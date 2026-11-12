#!/usr/bin/env python3
"""Recent wellness + daily training load dashboard (coach artifact)."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SLEEP_MAX = 10.0


def daily_load(activities: Path, start: str, end: str) -> pd.Series:
    by_day: dict[str, float] = defaultdict(float)
    with activities.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = row["start_date_local"][:10]
            if d < start or d > end:
                continue
            try:
                load = float(row.get("icu_training_load") or 0)
            except ValueError:
                load = 0.0
            by_day[d] += load
    idx = pd.to_datetime(sorted(by_day))
    return pd.Series([by_day[d.strftime("%Y-%m-%d")] for d in idx], index=idx)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("wellness_csv")
    p.add_argument("activities_csv", type=Path)
    p.add_argument("-o", type=Path, required=True)
    p.add_argument("--days", type=int, default=14)
    args = p.parse_args()
    args.o.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.wellness_csv, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    for c in ("restingHR", "hrv", "sleepSecs", "steps", "ctl", "atl"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["sleep_h"] = df["sleepSecs"] / 3600.0
    df.loc[df["sleep_h"] > SLEEP_MAX, "sleep_h"] = np.nan
    df["tsb"] = df["ctl"] - df["atl"]

    end = df.index.max()
    start = end - pd.Timedelta(days=args.days - 1)
    w = df.loc[df.index >= start].copy()
    start_s = start.strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")
    loads = daily_load(args.activities_csv, start_s, end_s)

    plt.style.use("seaborn-v0_8-whitegrid")
    fig = plt.figure(figsize=(12, 10))
    gs = fig.add_gridspec(3, 2, hspace=0.35, wspace=0.25)

    ax1 = fig.add_subplot(gs[0, :])
    ax1.bar(loads.index, loads.values, color="#6366f1", width=0.7, label="Daglig load (TSS)")
    ax1.set_ylabel("Load")
    ax1.set_title(f"Trening per dag ({start_s} → {end_s})")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    for i, (d, v) in enumerate(loads.items()):
        if v > 0:
            ax1.text(d, v + 3, f"{int(v)}", ha="center", fontsize=8)

    ax2 = fig.add_subplot(gs[1, 0])
    ax2.plot(w.index, w["hrv"], "o-", color="#059669", lw=2, markersize=6, label="HRV")
    med = w["hrv"].median()
    if not np.isnan(med):
        ax2.axhline(med, color="#059669", ls="--", alpha=0.5, label=f"median {med:.0f}")
    ax2.set_ylabel("HRV (ms)")
    ax2.set_title("HRV — hytte-helg markert")
    ax2.axvspan(pd.Timestamp("2026-10-24"), pd.Timestamp("2026-10-26"), alpha=0.15, color="#f59e0b")
    ax2.legend(fontsize=8)

    ax3 = fig.add_subplot(gs[1, 1])
    ax3.plot(w.index, w["restingHR"], "o-", color="#dc2626", lw=2, markersize=6)
    ax3.set_ylabel("RHR (bpm)")
    ax3.set_title("Hvilepuls")
    ax3.axvspan(pd.Timestamp("2026-10-24"), pd.Timestamp("2026-10-26"), alpha=0.15, color="#f59e0b")

    ax4 = fig.add_subplot(gs[2, 0])
    colors = ["#ef4444" if (s or 0) < 6 else "#3b82f6" for s in w["sleep_h"]]
    ax4.bar(w.index, w["sleep_h"], color=colors, width=0.7)
    ax4.axhline(7.5, color="#64748b", ls="--", alpha=0.7, label="mål 7,5 h")
    ax4.set_ylabel("Timer")
    ax4.set_title("Søvn")
    ax4.legend(fontsize=8)
    ax4.axvspan(pd.Timestamp("2026-10-24"), pd.Timestamp("2026-10-26"), alpha=0.1, color="#f59e0b")

    ax5 = fig.add_subplot(gs[2, 1])
    ax5.fill_between(w.index, w["ctl"], alpha=0.2, color="#2563eb")
    ax5.plot(w.index, w["ctl"], label="CTL", color="#2563eb", lw=2)
    ax5.plot(w.index, w["atl"], label="ATL", color="#dc2626", lw=1.5)
    ax5.plot(w.index, w["tsb"], label="TSB", color="#64748b", lw=1.2, ls="--")
    ax5.set_title("Fitness / fatigue")
    ax5.legend(fontsize=8)
    ax5.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))

    for ax in (ax1, ax2, ax3, ax4, ax5):
        ax.tick_params(axis="x", rotation=30)

    fig.suptitle("William — wellness + belastning (siste 14 dager)", fontsize=14, y=0.98)
    out = args.o / "hytte-uke-dashboard.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()

    # Steps only chart
    fig, ax = plt.subplots(figsize=(11, 3.5))
    ax.bar(w.index, w["steps"], color="#14b8a6", width=0.7)
    ax.set_title("Skritt per dag (hyttetur = ofte uten logget økt)")
    ax.set_ylabel("Skritt")
    ax.axvspan(pd.Timestamp("2026-10-24"), pd.Timestamp("2026-10-26"), alpha=0.15, color="#f59e0b")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    fig.savefig(args.o / "steps-14d.png", dpi=150, bbox_inches="tight")
    plt.close()

    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
