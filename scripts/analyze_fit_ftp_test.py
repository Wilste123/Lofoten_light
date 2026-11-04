#!/usr/bin/env python3
"""Deep FTP/ramp test report from .fit → PNG + markdown summary."""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from fitparse import FitFile

_REPO = Path(__file__).resolve().parents[1]


def load_series(path: Path) -> tuple[list[float], list[float], list[float], list[float], list[dict]]:
    fit = FitFile(str(path))
    session: dict = {}
    laps: list[dict] = []
    for msg in fit.get_messages("session"):
        for f in msg:
            if f.value is not None:
                session[f.name] = f.value
    for msg in fit.get_messages("lap"):
        laps.append({f.name: f.value for f in msg if f.value is not None})

    records: list[tuple] = []
    for msg in fit.get_messages("record"):
        d = {f.name: f.value for f in msg}
        if d.get("timestamp") is None:
            continue
        records.append(d)
    records.sort(key=lambda x: x["timestamp"])
    if not records:
        raise ValueError("No records in FIT")

    t0 = records[0]["timestamp"]
    mins, power, hr, cadence = [], [], [], []
    for d in records:
        elapsed = (d["timestamp"] - t0).total_seconds() / 60.0
        mins.append(elapsed)
        power.append(float(d["power"]) if d.get("power") is not None else np.nan)
        hr.append(float(d["heart_rate"]) if d.get("heart_rate") is not None else np.nan)
        cadence.append(float(d["cadence"]) if d.get("cadence") is not None else np.nan)

    return mins, power, hr, cadence, laps, session


def rolling_max(arr: np.ndarray, window: int) -> np.ndarray:
    out = np.full_like(arr, np.nan, dtype=float)
    q: deque[int] = deque()
    s = 0.0
    n_valid = 0
    for i, v in enumerate(arr):
        if np.isnan(v):
            continue
        q.append(int(v))
        s += v
        n_valid += 1
        while len(q) > window:
            s -= q.popleft()
            n_valid -= 1
        if n_valid >= max(window - 5, int(window * 0.9)):
            out[i] = s / len(q)
    return out


def best_window_avg(power: np.ndarray, window: int) -> tuple[float, int]:
    best, idx = 0.0, 0
    q: deque[int] = deque()
    s = 0
    for i, v in enumerate(power):
        if np.isnan(v):
            continue
        vi = int(v)
        q.append(vi)
        s += vi
        while len(q) > window:
            s -= q.popleft()
        if len(q) >= window - 5:
            avg = s / len(q)
            if avg > best:
                best, idx = avg, i
    return best, idx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fit_file", type=Path)
    parser.add_argument(
        "-o",
        type=Path,
        default=_REPO / "reports" / "tester" / "latest",
    )
    parser.add_argument("--ftp", type=float, default=200.0, help="Accepted FTP (W)")
    parser.add_argument("--weight-kg", type=float, default=82.6)
    args = parser.parse_args()

    mins, power, hr, cadence, laps, session = load_series(args.fit_file)
    p = np.array(power, dtype=float)
    h = np.array(hr, dtype=float)
    t = np.array(mins, dtype=float)

    out_dir = args.o
    out_dir.mkdir(parents=True, exist_ok=True)

    best_60, idx_60 = best_window_avg(p, 60)
    best_300, _ = best_window_avg(p, 300)
    best_1200, _ = best_window_avg(p, 1200)
    roll_60 = rolling_max(p, 60)

    # Lap boundaries in minutes from lap timestamps vs t0 - approximate from cumulative lap times
    lap_edges_min = [0.0]
    cum = 0.0
    for lap in laps:
        cum += float(lap.get("total_timer_time", 0)) / 60.0
        lap_edges_min.append(cum)

    ftp = args.ftp
    wkg = ftp / args.weight_kg

    # --- Figure 1: Power + HR ---
    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax1.plot(t, p, color="#2563eb", alpha=0.35, linewidth=0.6, label="Power (s)")
    ax1.plot(t, roll_60, color="#1d4ed8", linewidth=2, label="Rolling 60 s avg")
    for pct, col, lab in [
        (0.55, "#94a3b8", "55% FTP"),
        (0.75, "#64748b", "75% FTP"),
        (0.95, "#f59e0b", "95% FTP"),
        (1.0, "#dc2626", "100% FTP"),
    ]:
        ax1.axhline(ftp * pct, color=col, linestyle="--", linewidth=0.8, alpha=0.7)
    ax1.axhline(best_60, color="#7c3aed", linestyle="-.", linewidth=1.2, label=f"Best 60 s {best_60:.0f} W")
    ax1.set_ylabel("Power (W)")
    ax1.set_xlabel("Minutter fra start")
    ax1.set_title("FTP-test 3. nov 2026 — power og rolling 60 s")
    ax1.set_xlim(0, t[-1])
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper left", fontsize=8)

    ax2 = ax1.twinx()
    ax2.plot(t, h, color="#ef4444", alpha=0.5, linewidth=0.8, label="HR")
    ax2.set_ylabel("Puls (bpm)")
    ax2.set_ylim(80, 190)

    for i, edge in enumerate(lap_edges_min[1:-1], start=1):
        ax1.axvline(edge, color="#059669", linestyle=":", alpha=0.6)
    fig.tight_layout()
    fig.savefig(out_dir / "ftp-test-power-hr.png", dpi=150)
    plt.close(fig)

    # --- Figure 2: Zone time bar (accepted FTP) ---
    zones = [
        ("Z1 <55%", 0, 0.55),
        ("Z2", 0.55, 0.75),
        ("Z3", 0.75, 0.90),
        ("Z4", 0.90, 1.05),
        ("Z5", 1.05, 1.20),
        ("Z5+", 1.20, 10),
    ]
    valid = p[~np.isnan(p)]
    total_s = len(valid)
    counts = []
    for _, lo, hi in zones:
        counts.append(np.sum((valid >= ftp * lo) & (valid < ftp * hi)) / total_s * 100)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh([z[0] for z in zones], counts, color=["#cbd5e1", "#93c5fd", "#60a5fa", "#fbbf24", "#f97316", "#dc2626"])
    ax.set_xlabel("% av tid med power-data")
    ax.set_title(f"Tid i soner (FTP {ftp:.0f} W)")
    fig.tight_layout()
    fig.savefig(out_dir / "ftp-test-zone-time.png", dpi=150)
    plt.close(fig)

    # --- Figure 3: Best efforts table as text figure ---
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.axis("off")
    rows = [
        ["Metrikk", "Verdi", "FTP-estimat (metode)"],
        ["Best 60 s", f"{best_60:.0f} W", f"×0.75 ramp ≈ {best_60*0.75:.0f} W"],
        ["Best 5 min", f"{best_300:.0f} W", "—"],
        ["Best 20 min", f"{best_1200:.0f} W", f"×0.95 ≈ {best_1200*0.95:.0f} W"],
        ["Max sekund", f"{np.nanmax(valid):.0f} W", "—"],
        ["Snitt power", f"{np.nanmean(valid):.0f} W", "—"],
        ["HR snitt / max", f"{np.nanmean(h[~np.isnan(h)]):.0f} / {np.nanmax(h):.0f} bpm", "—"],
        ["TP FTP (valgt)", f"{ftp:.0f} W", f"{wkg:.2f} W/kg @ {args.weight_kg} kg"],
        ["FIT TSS", f"{session.get('training_stress_score', 'n/a')}", "—"],
    ]
    table = ax.table(cellText=rows, loc="center", cellLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.4)
    fig.savefig(out_dir / "ftp-test-summary-table.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    summary = {
        "file": str(args.fit_file),
        "start": str(session.get("start_time")),
        "duration_min": float(session.get("total_timer_time", 0)) / 60,
        "distance_km": float(session.get("total_distance", 0)) / 1000,
        "best_60s_w": round(best_60),
        "best_5min_w": round(best_300),
        "best_20min_w": round(best_1200),
        "ftp_accepted_w": ftp,
        "w_per_kg": round(wkg, 2),
        "tss_fit": session.get("training_stress_score"),
        "lap_minutes": lap_edges_min,
    }
    (out_dir / "ftp-test-metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md = f"""# FTP-test analyse — 3. nov 2026

**Fil:** `{args.fit_file.name}`  
**Varighet:** {summary['duration_min']:.0f} min · **Distanse:** {summary['distance_km']:.1f} km  
**Valgt FTP (TP):** **{ftp:.0f} W** ({wkg:.2f} W/kg @ {args.weight_kg} kg)

## Nøkkeltall (.fit)

| Metrikk | Verdi |
|---------|------:|
| Best 60 s | **{best_60:.0f} W** |
| Best 5 min | **{best_300:.0f} W** |
| Best 20 min | **{best_1200:.0f} W** |
| HR snitt / max | {np.nanmean(h[~np.isnan(h)]):.0f} / {np.nanmax(h):.0f} bpm |
| TSS (session) | {session.get('training_stress_score', '—')} |

## Grafer

- `ftp-test-power-hr.png`
- `ftp-test-zone-time.png`
- `ftp-test-summary-table.png`
"""
    (out_dir / "ftp-test-analyse.md").write_text(md, encoding="utf-8")
    print(f"Wrote report to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
