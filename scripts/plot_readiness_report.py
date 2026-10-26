#!/usr/bin/env python3
"""TB-Score charts: trend (morgen/kveld), komponenter, dashboard."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

from analyze_tp_export import load_rows  # noqa: E402
from readiness_total_load import (  # noqa: E402
    compute_readiness_at,
    load_config,
    parse_activity_points,
    parse_wellness_rows,
    resolve_as_of,
    result_to_dict,
)

_REPO = Path(__file__).resolve().parents[1]
BAND_GREEN = 78
BAND_YELLOW = 58


def _band_color(score: float) -> str:
    if score >= BAND_GREEN:
        return "#16a34a"
    if score >= BAND_YELLOW:
        return "#ca8a04"
    return "#dc2626"


def build_score_series(
    days,
    activities,
    cfg,
    morning: time = time(7, 0),
    evening: time = time(17, 0),
) -> pd.DataFrame:
    rows: list[dict] = []
    for d in days:
        base = d.date.replace(hour=0, minute=0, second=0, microsecond=0)
        for label, t in (("morgen", morning), ("kveld", evening)):
            at = base.replace(hour=t.hour, minute=t.minute)
            r = compute_readiness_at(at, days, activities, cfg, False)
            rows.append(
                {
                    "datetime": at,
                    "date": at.date(),
                    "tid": label,
                    "tb_score": r.score,
                    "band": r.band,
                }
            )
    return pd.DataFrame(rows)


def plot_tb_trend(df: pd.DataFrame, out: Path, cfg: dict) -> None:
    bands = cfg.get("bands") or {}
    green = int(bands.get("green_min", BAND_GREEN))
    yellow = int(bands.get("yellow_min", BAND_YELLOW))

    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.axhspan(yellow, 100, color="#22c55e", alpha=0.12, zorder=0)
    ax.axhspan(0, yellow, color="#ef4444", alpha=0.10, zorder=0)
    ax.axhspan(yellow, green, color="#eab308", alpha=0.12, zorder=0)
    ax.axhline(green, color="#16a34a", lw=0.8, ls="--", alpha=0.6)
    ax.axhline(yellow, color="#ca8a04", lw=0.8, ls="--", alpha=0.6)

    for tid, color, marker in (
        ("morgen", "#2563eb", "o"),
        ("kveld", "#7c3aed", "s"),
    ):
        sub = df[df["tid"] == tid]
        ax.plot(
            sub["datetime"],
            sub["tb_score"],
            label=f"TB kl. {tid}",
            color=color,
            marker=marker,
            ms=4,
            lw=1.4,
        )

    ax.set_ylim(0, 100)
    ax.set_ylabel("TB-Score")
    ax.set_title("Totalbelastning (TB-Score) — morgen vs kveld")
    ax.legend(loc="upper left")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_components(latest: dict, out: Path) -> None:
    comps = latest.get("components") or []
    if not comps:
        return
    labels = [c["label"] for c in comps]
    scores = [c["score"] for c in comps if c["score"] is not None]
    labels = [c["label"] for c in comps if c["score"] is not None]
    colors = [_band_color(s) for s in scores]

    fig, ax = plt.subplots(figsize=(9, max(3.5, len(labels) * 0.45)))
    y = np.arange(len(labels))
    ax.barh(y, scores, color=colors, alpha=0.85)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlim(0, 100)
    ax.axvline(BAND_YELLOW, color="#ca8a04", ls="--", lw=0.8, alpha=0.5)
    ax.axvline(BAND_GREEN, color="#16a34a", ls="--", lw=0.8, alpha=0.5)
    as_of = latest.get("as_of", "?")
    ax.set_title(f"TB-komponenter — snapshot {as_of} (total {latest.get('tb_score')})")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_dashboard(
    wellness_df: pd.DataFrame,
    tb_df: pd.DataFrame,
    latest: dict,
    out: Path,
) -> None:
    fig = plt.figure(figsize=(12, 8))
    gs = fig.add_gridspec(2, 2, hspace=0.35, wspace=0.25)

    ax1 = fig.add_subplot(gs[0, 0])
    ax1.plot(wellness_df.index, wellness_df["ctl"], label="CTL", color="#2563eb", lw=1.2)
    ax1.plot(wellness_df.index, wellness_df["atl"], label="ATL", color="#dc2626", lw=1.0)
    ax1.set_title("Fitness / fatigue")
    ax1.legend(fontsize=8)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))

    ax2 = fig.add_subplot(gs[0, 1])
    eve = tb_df[tb_df["tid"] == "kveld"]
    colors = [_band_color(s) for s in eve["tb_score"]]
    ax2.scatter(eve["datetime"], eve["tb_score"], c=colors, s=28, zorder=3)
    ax2.plot(eve["datetime"], eve["tb_score"], color="#64748b", lw=0.8, alpha=0.6)
    ax2.axhspan(BAND_YELLOW, 100, color="#22c55e", alpha=0.08)
    ax2.axhspan(0, BAND_YELLOW, color="#ef4444", alpha=0.08)
    ax2.set_ylim(0, 100)
    ax2.set_title("TB-Score (kveld)")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))

    ax3 = fig.add_subplot(gs[1, 0])
    comps = [c for c in (latest.get("components") or []) if c.get("score") is not None]
    if comps:
        ax3.barh(
            [c["label"][:22] for c in comps],
            [c["score"] for c in comps],
            color=[_band_color(c["score"]) for c in comps],
        )
        ax3.set_xlim(0, 100)
    ax3.set_title("Nå — komponenter")

    ax4 = fig.add_subplot(gs[1, 1])
    ax4.axis("off")
    score = latest.get("tb_score", "—")
    band = latest.get("band", "")
    rec = latest.get("recommendation", "")
    acute = latest.get("acute") or {}
    lines = [
        f"TB-Score: {score}/100 ({band})",
        f"Tidspunkt: {latest.get('as_of', '—')}",
        "",
        rec[:280] + ("…" if len(rec) > 280 else ""),
    ]
    if acute.get("hours_since_last") is not None:
        lines.extend(
            [
                "",
                f"Siste økt: {acute.get('last_sport')} "
                f"({acute.get('hours_since_last'):.1f} t siden)",
                f"Load 24h: {acute.get('load_24h', 0):.0f}",
            ]
        )
    ax4.text(
        0.05,
        0.95,
        "\n".join(lines),
        va="top",
        fontsize=10,
        family="sans-serif",
        transform=ax4.transAxes,
    )
    fig.suptitle("TB-Score dashboard — totalbelastning", fontsize=13, y=0.98)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def load_wellness_frame(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    for col in ("ctl", "atl"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description="Plot TB-Score readiness report")
    parser.add_argument("wellness_csv", type=Path)
    parser.add_argument("--activities", type=Path, required=True)
    parser.add_argument("-o", "--output-dir", type=Path, default=_REPO / "reports/readiness")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--days", type=int, default=0, help="Trim to last N calendar days")
    args = parser.parse_args()

    if not args.wellness_csv.is_file():
        print(f"Missing {args.wellness_csv}", file=sys.stderr)
        return 1
    if not args.activities.is_file():
        print(f"Missing {args.activities}", file=sys.stderr)
        return 1

    cfg = load_config(args.config)
    rows, fields = load_rows(args.wellness_csv)
    days = parse_wellness_rows(rows, fields)
    if args.days > 0 and days:
        cutoff = days[-1].date.date() - timedelta(days=args.days)
        days = [d for d in days if d.date.date() >= cutoff]

    a_rows, a_fields = load_rows(args.activities)
    activities = parse_activity_points(a_rows, a_fields)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    tb_df = build_score_series(days, activities, cfg)
    wellness_df = load_wellness_frame(args.wellness_csv)
    if args.days > 0 and len(wellness_df):
        cutoff = wellness_df.index.max() - pd.Timedelta(days=args.days)
        wellness_df = wellness_df.loc[wellness_df.index >= cutoff]

    as_of = resolve_as_of("now", cfg)
    latest = result_to_dict(
        compute_readiness_at(as_of, days, activities, cfg, False)
    )

    plot_tb_trend(tb_df, args.output_dir / "tb-score-trend.png", cfg)
    plot_components(latest, args.output_dir / "tb-components-now.png")
    plot_dashboard(wellness_df, tb_df, latest, args.output_dir / "tb-dashboard.png")

    # Gauge-style single number
    fig, ax = plt.subplots(figsize=(5, 3))
    score = float(latest.get("tb_score", 0))
    ax.barh([0], [score], color=_band_color(score), height=0.5)
    ax.barh([0], [100 - score], left=[score], color="#e2e8f0", height=0.5)
    ax.set_xlim(0, 100)
    ax.set_yticks([])
    ax.set_title(f"TB-Score nå: {score:.0f} ({latest.get('band')})")
    for x, label in ((BAND_YELLOW, "gul"), (BAND_GREEN, "grønn")):
        ax.axvline(x, color="#94a3b8", ls=":", lw=0.8)
    fig.tight_layout()
    fig.savefig(args.output_dir / "tb-score-now.png", dpi=150)
    plt.close(fig)

    legend = [
        Patch(facecolor="#22c55e", alpha=0.3, label=f"Grønn ≥{BAND_GREEN}"),
        Patch(facecolor="#eab308", alpha=0.3, label=f"Gul {BAND_YELLOW}–{BAND_GREEN - 1}"),
        Patch(facecolor="#ef4444", alpha=0.3, label=f"Rød <{BAND_YELLOW}"),
    ]
    fig, ax = plt.subplots(figsize=(4, 0.4))
    ax.legend(handles=legend, loc="center", ncol=3, frameon=False)
    ax.axis("off")
    fig.savefig(args.output_dir / "tb-legend.png", dpi=100, bbox_inches="tight")
    plt.close(fig)

    print(f"Wrote charts to {args.output_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
