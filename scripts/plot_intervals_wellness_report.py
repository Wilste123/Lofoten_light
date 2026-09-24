#!/usr/bin/env python3
"""12-month wellness charts + best-case forecast (Intervals.icu CSV)."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, median

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[1]

# Garmin/Intervals sleep often duplicates or inflates "time in bed"
SLEEP_HOURS_MAX_TRUST = 10.0
SLEEP_TARGET_BEST = 7.75  # h/night best-case steady state
WEIGHT_TARGET_BAND = (87.0, 90.0)  # kg — performance maintenance (profile ~89)
CTL_TARGET_12M_BEST = 55.0  # conservative aerobic base, not 2019 hero CTL


def load_wellness(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    for col in ("ctl", "atl", "rampRate", "weight", "restingHR", "sleepSecs", "steps"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "sleepSecs" in df.columns:
        df["sleep_h"] = df["sleepSecs"] / 3600.0
        df.loc[df["sleep_h"] > SLEEP_HOURS_MAX_TRUST, "sleep_h"] = np.nan
    return df


def weekly_series(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col].resample("W").mean()


def forecast_dates(last: date, months: int = 12) -> pd.DatetimeIndex:
    start = last + timedelta(days=1)
    end = last + timedelta(days=365)
    return pd.date_range(start=start, end=end, freq="D")


def best_case_ctl(dates: pd.DatetimeIndex, ctl_now: float) -> pd.Series:
    """Logistic-style ramp toward CTL_TARGET_12M_BEST (best-case consistency)."""
    t = np.linspace(0, 1, len(dates))
    # Smooth S-curve: faster early re-establishment, plateaus near target
    k = 8.0
    mid = 0.35
    frac = 1 / (1 + np.exp(-k * (t - mid)))
    values = ctl_now + (CTL_TARGET_12M_BEST - ctl_now) * frac
    return pd.Series(values, index=dates)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=_REPO / "reports/wellness",
    )
    parser.add_argument("--months-back", type=int, default=12)
    args = parser.parse_args()
    if not args.csv_path.is_file():
        print(f"Missing: {args.csv_path}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    df = load_wellness(args.csv_path)
    last_day = df.index.max().date()
    first_day = df.index.min().date()

    # --- Figure 1: CTL / ATL ---
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(df.index, df["ctl"], label="CTL (fitness)", color="#2563eb", lw=1.2)
    ax.plot(df.index, df["atl"], label="ATL (fatigue)", color="#dc2626", lw=1.0, alpha=0.85)
    ax.set_ylabel("Load")
    ax.set_title("Intervals.icu — CTL / ATL (12 mnd)")
    ax.legend(loc="upper left")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(args.output_dir / "ctl-atl-12m.png", dpi=150)
    plt.close(fig)

    # Forecast CTL
    f_dates = forecast_dates(last_day)
    ctl_now = float(df["ctl"].dropna().iloc[-1]) if df["ctl"].notna().any() else 0.0
    ctl_fc = best_case_ctl(f_dates, ctl_now)

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(df.index, df["ctl"], label="CTL faktisk", color="#2563eb", lw=1.2)
    ax.plot(ctl_fc.index, ctl_fc.values, label="CTL best-case (prognose)", color="#16a34a", lw=2, ls="--")
    ax.axhline(CTL_TARGET_12M_BEST, color="#16a34a", alpha=0.25, ls=":")
    ax.set_ylabel("CTL")
    ax.set_title("CTL — historikk + best-case neste 12 mnd")
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(args.output_dir / "ctl-forecast-12m.png", dpi=150)
    plt.close(fig)

    # --- Sleep ---
    sleep_pts = df["sleep_h"].dropna()
    sleep_w = weekly_series(df, "sleep_h").dropna()

    fig, ax = plt.subplots(figsize=(11, 4))
    if len(sleep_pts):
        ax.scatter(sleep_pts.index, sleep_pts.values, s=18, alpha=0.6, label="Søvn (dager med data)")
    if len(sleep_w):
        ax.plot(sleep_w.index, sleep_w.values, color="#7c3aed", lw=2, label="Ukesnitt")
    ax.axhspan(7.0, 8.5, alpha=0.12, color="#16a34a", label="Best-case sone 7–8,5 t")
    ax.axhline(SLEEP_TARGET_BEST, color="#16a34a", ls="--", alpha=0.7)
    # forecast flat best-case
    ax.plot(
        f_dates,
        [SLEEP_TARGET_BEST] * len(f_dates),
        color="#16a34a",
        lw=1.5,
        ls=":",
        label="Prognose (best-case)",
    )
    ax.set_ylabel("Timer søvn")
    ax.set_title("Søvn — filtrert (ekskl. >10 t som feil)")
    ax.legend(loc="upper right", fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(args.output_dir / "sleep-12m-forecast.png", dpi=150)
    plt.close(fig)

    # --- Weight ---
    w = df["weight"].dropna()
    fig, ax = plt.subplots(figsize=(11, 4))
    if len(w):
        ax.plot(w.index, w.values, "o-", color="#ca8a04", label="Vekt (måledager)")
    ax.axhspan(WEIGHT_TARGET_BAND[0], WEIGHT_TARGET_BAND[1], alpha=0.15, color="#16a34a")
    mid_w = mean(WEIGHT_TARGET_BAND)
    ax.plot(f_dates, [mid_w] * len(f_dates), ls="--", color="#16a34a", label="Best-case stabil ~88–90 kg")
    ax.set_ylabel("kg")
    ax.set_title("Vekt — sparsom historikk + best-case")
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(args.output_dir / "weight-12m-forecast.png", dpi=150)
    plt.close(fig)

    # --- RHR ---
    rhr = df["restingHR"].dropna()
    if len(rhr) >= 3:
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.plot(rhr.index, rhr.values, "o-", color="#e11d48", label="Hvilepuls")
        target = min(58.0, float(median(rhr.values)))  # profile antatt 58
        ax.plot(f_dates, [target] * len(f_dates), ls="--", color="#16a34a", label=f"Best-case ~{target:.0f} bpm")
        ax.set_ylabel("bpm")
        ax.set_title("Hvilepuls")
        ax.legend()
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(args.output_dir / "rhr-12m-forecast.png", dpi=150)
        plt.close(fig)

    # Markdown report
    n_sleep = int(df["sleep_h"].notna().sum())
    n_weight = int(df["weight"].notna().sum())
    n_rhr = int(df["restingHR"].notna().sum())
    sleep_vals = df["sleep_h"].dropna()
    report = f"""# Wellness 12 mnd + best-case prognose

**Kilde:** `{args.csv_path.name}` (Intervals.icu wellness.csv)  
**Periode faktisk:** {first_day} → {last_day}  
**Prognose:** {last_day + timedelta(days=1)} → {last_day + timedelta(days=365)}  

## Datakvalitet (viktig)

| Metrikk | Dager med data | Merknad |
|---------|----------------|---------|
| CTL/ATL | {int(df['ctl'].notna().sum())} / {len(df)} | Komplett — belastning fra økter |
| Søvn | {n_sleep} / {len(df)} | Mange verdier **>10 t** (sannsynlig Garmin/«time in bed») — filtrert i grafer |
| Vekt | {n_weight} | Svært få punkter — ikke bruk til harde mål |
| Hvilepuls | {n_rhr} | Begrenset |
| HRV / readiness | 0 | Ikke synket til Intervals |

**Konklusjon:** Grafer og prognose for søvn/vekt er **best-case antakelser** + det sparse som finnes. For OPV-oppfølging: få Garmin til å fylle Wellness daglig.

## Faktisk (12 mnd)

- **CTL nå:** {ctl_now:.1f} (topp i perioden {float(df['ctl'].max()):.1f})
- **ATL nå:** {float(df['atl'].dropna().iloc[-1]):.1f}
"""
    if len(sleep_vals):
        report += f"- **Søvn (filtrert ≤10 t):** snitt {sleep_vals.mean():.1f} t, median {sleep_vals.median():.1f} t på {len(sleep_vals)} dager\n"
    if len(w):
        report += f"- **Vekt:** {w.min():.1f}–{w.max():.1f} kg (sist {w.iloc[-1]:.1f} kg)\n"

    report += f"""
## Best-case prognose neste 12 mnd (Half Extreme-grunnmur)

Dette er **ikke** statistisk ML — det er «hvis du gjør det riktige»:

| Område | Best-case mål | Begrunnelse |
|--------|---------------|-------------|
| **CTL** | ~{CTL_TARGET_12M_BEST:.0f} ved sep 2027 | Jevn ~14–15 t/uke, skadefri opptrapping (ikke 2019) |
| **Søvn** | {SLEEP_TARGET_BEST:.1f} t/snitt | `knowledge/restitusjon/sovn-stress.md` |
| **Vekt** | {WEIGHT_TARGET_BAND[0]:.0f}–{WEIGHT_TARGET_BAND[1]:.0f} kg | Vedlikehold styrke + volum |
| **Wellness-logging** | >300 dager/år med sønn+RHR | Nødvendig for OPV justering |

### Risiko hvis data forblir tom

Uten wellness i Intervals coach må fortsatt stole på **dine TP-kommentarer** — CTL alene skjuler dårlig søvn og stress.

## Grafer

- `ctl-atl-12m.png`
- `ctl-forecast-12m.png`
- `sleep-12m-forecast.png`
- `weight-12m-forecast.png`
"""
    if len(rhr) >= 3:
        report += "- `rhr-12m-forecast.png`\n"

    (args.output_dir / "wellness-12m-report.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWrote charts + report to {args.output_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
