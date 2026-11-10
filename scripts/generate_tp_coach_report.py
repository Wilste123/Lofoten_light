#!/usr/bin/env python3
"""Coach rapport kun fra TrainingPeaks (tpapi): PMC, økter, soner — ingen Intervals."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO = _SCRIPT_DIR.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from tp_lib import (  # noqa: E402
    athlete_id,
    get_performance_data,
    get_workout_details,
    get_workouts_tpapi_raw,
)

TP_MAX_RANGE_DAYS = 45


def _chunk_ranges(start: date, end: date) -> list[tuple[date, date]]:
    """Inclusive chunks of at most TP_MAX_RANGE_DAYS."""
    out: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=TP_MAX_RANGE_DAYS - 1), end)
        out.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return out


def fetch_pmc(start: date, end: date) -> pd.DataFrame:
    rows: list[dict] = []
    for a, b in _chunk_ranges(start, end):
        for row in get_performance_data(a.isoformat(), b.isoformat()):
            rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["workoutDay"].str[:10])
    for c in ("ctl", "atl", "tsb", "tssActual", "tssPlanned"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("date").drop_duplicates("date", keep="last")


def fetch_workouts(start: date, end: date) -> list[dict]:
    seen: set[int] = set()
    out: list[dict] = []
    for a, b in _chunk_ranges(start, end):
        for w in get_workouts_tpapi_raw(a.isoformat(), b.isoformat()):
            wid = w.get("workoutId")
            if wid in seen:
                continue
            seen.add(wid)
            out.append(w)
    out.sort(key=lambda w: (w.get("workoutDay") or "", w.get("startTime") or ""))
    return out


def workouts_df(workouts: list[dict]) -> pd.DataFrame:
    rows = []
    for w in workouts:
        day = (w.get("workoutDay") or "")[:10]
        if not day:
            continue
        tss = w.get("tssActual")
        if tss is None or tss == 0:
            continue
        rows.append(
            {
                "date": day,
                "workout_id": w.get("workoutId"),
                "title": w.get("title") or "",
                "type_id": w.get("workoutTypeValueId"),
                "tss": float(tss),
                "hours": float(w.get("totalTime") or 0),
                "if": w.get("if"),
                "np": w.get("normalizedPowerActual"),
                "avg_power": w.get("powerAverage"),
                "avg_hr": w.get("heartRateAverage"),
                "max_hr": w.get("heartRateMaximum"),
                "distance_km": (float(w.get("distance") or 0) / 1000),
                "feeling": w.get("feeling"),
                "rpe": w.get("rpe"),
                "description": (w.get("description") or "")[:200],
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def _plot_zone_bars(ax, zone_payload: dict | None, title: str, unit: str) -> None:
    if not zone_payload or not zone_payload.get("timeInZones"):
        ax.set_title(f"{title} (ingen sonedata)")
        return
    zones = zone_payload["timeInZones"]
    labels = [f"Z{z.get('label','?')}" for z in zones]
    mins = [float(z.get("seconds") or 0) / 60 for z in zones]
    ax.barh(labels, mins, color=plt.cm.viridis(np.linspace(0.15, 0.85, len(labels))))
    ax.set_xlabel(f"min ({unit})")
    ax.set_title(title)


def pick_key_workouts(workouts: list[dict]) -> list[dict]:
    """Velg nøkkeløkter for dybde (høy TSS + navn/markører)."""
    completed = [w for w in workouts if (w.get("tssActual") or 0) > 0]
    keys: list[dict] = []
    used: set[int] = set()

    def add(w: dict) -> None:
        wid = w.get("workoutId")
        if wid in used:
            return
        used.add(wid)
        keys.append(w)

    title_rules = [
        ("ftp", lambda t: "ftp" in t),
        ("firda", lambda t: "firda" in t or "6×4" in t or "6x4" in t),
        ("sweet", lambda t: "sweet" in t or "sweetspot" in t),
        ("6x3", lambda t: "6x3" in t or "6×3" in t),
        ("5x3", lambda t: "5x3" in t or "5×3" in t),
        ("7x2", lambda t: "7x2" in t or "7×2" in t),
    ]
    lowered = [(w, (w.get("title") or "").lower()) for w in completed]
    for _tag, pred in title_rules:
        for w, t in lowered:
            if pred(t):
                add(w)
                break
    by_tss = sorted(completed, key=lambda w: float(w.get("tssActual") or 0), reverse=True)
    for w in by_tss:
        if len(keys) >= 8:
            break
        tid = w.get("workoutTypeValueId")
        if tid == 2 and w not in keys:
            add(w)
    for w in by_tss:
        if w.get("workoutTypeValueId") == 3:
            add(w)
            if len(keys) >= 6:
                break
    return keys[:8]


def plot_reports(
    pmc: pd.DataFrame,
    wdf: pd.DataFrame,
    key_workouts: list[dict],
    out_dir: Path,
) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    if not pmc.empty:
        fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
        axes[0].plot(pmc["date"], pmc["ctl"], "b-", lw=2, label="Fitness (CTL)")
        axes[0].plot(pmc["date"], pmc["atl"], "r-", lw=1.5, label="Fatigue (ATL)")
        axes[0].legend()
        axes[0].set_ylabel("Load")
        axes[0].set_title("TrainingPeaks — Fitness / Fatigue")
        axes[1].plot(pmc["date"], pmc["tsb"], "g-", lw=2)
        axes[1].axhline(0, color="gray", ls=":")
        axes[1].fill_between(
            pmc["date"], pmc["tsb"], 0, where=pmc["tsb"] < 0, alpha=0.25, color="red"
        )
        axes[1].set_ylabel("Form (TSB)")
        axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        fig.autofmt_xdate()
        fig.tight_layout()
        p = out_dir / "tp8-pmc.png"
        fig.savefig(p, dpi=140)
        plt.close(fig)
        written.append(p.name)

    if not wdf.empty:
        wdf = wdf.copy()
        wdf["week"] = wdf["date"].dt.isocalendar().week
        wdf["year"] = wdf["date"].dt.isocalendar().year
        wk = wdf.groupby(["year", "week"], as_index=False).agg(
            tss=("tss", "sum"), hours=("hours", "sum")
        )
        fig, ax1 = plt.subplots(figsize=(10, 4))
        x = range(len(wk))
        ax1.bar(x, wk["tss"], color="#2563eb", alpha=0.85)
        ax1.set_ylabel("TSS (TP)")
        ax2 = ax1.twinx()
        ax2.plot(x, wk["hours"], "o-", color="#f97316")
        ax2.set_ylabel("Timer")
        ax1.set_xticks(x)
        ax1.set_xticklabels([f"W{r['week']}" for _, r in wk.iterrows()])
        ax1.set_title("Ukelast — kun TrainingPeaks TSS")
        fig.tight_layout()
        p = out_dir / "tp8-weekly-load.png"
        fig.savefig(p, dpi=140)
        plt.close(fig)
        written.append(p.name)

        feel = wdf.dropna(subset=["feeling"])
        if not feel.empty:
            fig, ax = plt.subplots(figsize=(10, 3.5))
            ax.plot(feel["date"], feel["feeling"], "o", alpha=0.7, label="Feeling (TP)")
            ax2 = ax.twinx()
            rpe = wdf.dropna(subset=["rpe"])
            if not rpe.empty:
                ax2.plot(rpe["date"], rpe["rpe"], "s", color="orange", alpha=0.5, label="RPE")
            ax.set_ylabel("Feeling 1–5")
            ax.set_title("Subjektivt i TP (per økt) — ikke søvn/HRV")
            fig.tight_layout()
            p = out_dir / "tp8-feeling-rpe.png"
            fig.savefig(p, dpi=140)
            plt.close(fig)
            written.append(p.name)

    n = len(key_workouts)
    if n:
        fig, axes = plt.subplots(n, 2, figsize=(12, 2.8 * n))
        if n == 1:
            axes = np.array([axes])
        aid = athlete_id()
        for i, w in enumerate(key_workouts):
            wid = w["workoutId"]
            day = (w.get("workoutDay") or "")[:10]
            title = f"{day} {w.get('title', '')[:40]}"
            det = get_workout_details(wid)
            extras = []
            if w.get("powerAverage"):
                extras.append(f"ØW {w['powerAverage']}")
            if w.get("normalizedPowerActual"):
                extras.append(f"NP {w['normalizedPowerActual']}")
            if w.get("heartRateAverage"):
                extras.append(f"ØP {w['heartRateAverage']}")
            if w.get("tssActual"):
                extras.append(f"TSS {w['tssActual']:.0f}")
            full_title = title + (" | " + ", ".join(extras) if extras else "")
            _plot_zone_bars(
                axes[i, 0],
                det.get("timeInPowerZones"),
                full_title + " — wattsoner",
                "W",
            )
            _plot_zone_bars(
                axes[i, 1],
                det.get("timeInHeartRateZones"),
                full_title + " — puls",
                "bpm",
            )
            mm = (det.get("meanMaxPowers") or {}).get("meanMaxes")
            if mm and w.get("powerAverage"):
                fig2, axm = plt.subplots(figsize=(6, 3))
                labels, vals = [], []
                order = [
                    "MM5Seconds",
                    "MM1Minute",
                    "MM5Minutes",
                    "MM20Minutes",
                    "MM1Hour",
                ]
                by_label = {m["label"]: m.get("value") for m in mm if m.get("value")}
                for lab in order:
                    if lab in by_label:
                        labels.append(lab.replace("MM", ""))
                        vals.append(by_label[lab])
                if vals:
                    axm.bar(labels, vals, color="#0ea5e9")
                    axm.set_ylabel("W")
                    axm.set_title(f"Mean-max power — {w.get('title', '')[:30]}")
                    fig2.tight_layout()
                    mp = out_dir / f"tp8-mmp-{wid}.png"
                    fig2.savefig(mp, dpi=120)
                    plt.close(fig2)
                    written.append(mp.name)
        fig.tight_layout()
        p = out_dir / "tp8-key-sessions-zones.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        written.append(p.name)

    return written


def write_markdown(
    start: date,
    end: date,
    pmc: pd.DataFrame,
    wdf: pd.DataFrame,
    key_workouts: list[dict],
    charts: list[str],
    out_path: Path,
) -> None:
    last = pmc.iloc[-1] if not pmc.empty else None
    lines = [
        f"# 8-ukers analyse — kun TrainingPeaks ({start} → {end})",
        "",
        "**Kilde:** tpapi (`performancedata` + `fitness/v6` + økt `/details`). **Ingen Intervals.**",
        "",
        "**Wellness (søvn, HRV, daglig vekt):** ikke tilgjengelig med `Production_tpAuth` "
        "(krever Partners JWT → `/v2/metrics`). Under: **PMC + TSS + soner + Feeling/RPE fra økter**.",
        "",
    ]
    if last is not None:
        lines += [
            "## PMC (i dag)",
            f"- **Fitness:** {last['ctl']:.0f}",
            f"- **Fatigue:** {last['atl']:.0f}",
            f"- **Form:** {last['tsb']:.0f}",
            "",
        ]
    if not wdf.empty:
        lines += [
            "## Volum",
            f"- Økter med TSS: **{len(wdf)}**",
            f"- Sum TSS: **{wdf['tss'].sum():.0f}**",
            f"- Sum timer (TP `totalTime`): **{wdf['hours'].sum():.1f} h**",
            "",
        ]
    lines += ["## Grafer", ""]
    for c in charts:
        lines.append(f"- `{c}`")
    lines += ["", "## Nøkkeløkter (TP-detaljer)", ""]
    for w in key_workouts:
        day = (w.get("workoutDay") or "")[:10]
        lines.append(f"### {day} — {w.get('title', '')}")
        lines.append(
            f"TSS **{w.get('tssActual')}**, IF **{w.get('if')}**, "
            f"NP **{w.get('normalizedPowerActual')}**, ØW **{w.get('powerAverage')}**, "
            f"ØP **{w.get('heartRateAverage')}**, max **{w.get('heartRateMaximum')}**."
        )
        if w.get("description"):
            lines.append(f"> {w['description'][:300]}")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=56)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_REPO / "reports/coach",
    )
    parser.add_argument("--end", help="YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    end = date.fromisoformat(args.end) if args.end else date.today()
    start = end - timedelta(days=args.days - 1)
    tag = end.isoformat()
    out_dir = args.output / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    pmc = fetch_pmc(start, end)
    workouts = fetch_workouts(start, end)
    wdf = workouts_df(workouts)
    keys = pick_key_workouts(workouts)

    data_dir = _REPO / "data/trainingpeaks/exports"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / f"tp-workouts-raw-{tag}.json").write_text(
        json.dumps(workouts, indent=2), encoding="utf-8"
    )
    pmc.to_json(data_dir / f"tp-pmc-{tag}.json", orient="records", indent=2)

    charts = plot_reports(pmc, wdf, keys, out_dir)
    md = out_dir / "analyse-8uker-tp-only.md"
    write_markdown(start, end, pmc, wdf, keys, charts, md)
    latest = args.output / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink(missing_ok=True)
    try:
        latest.symlink_to(tag, target_is_directory=True)
    except OSError:
        pass

    if not pmc.empty:
        last = pmc.iloc[-1]
        print(
            f"TP {tag}: Fitness {last['ctl']:.0f}, "
            f"Fatigue {last['atl']:.0f}, Form {last['tsb']:.0f}"
        )
    print(f"Økter: {len(workouts)} raw, {len(wdf)} med TSS")
    print(f"Rapport: {md}")
    print(f"Grafer: {out_dir}/ ({', '.join(charts)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
