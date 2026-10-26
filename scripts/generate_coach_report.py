#!/usr/bin/env python3
"""Standard coach rapport: wellness + aktiviteter → TB-Score tekst + grafer."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[1]
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from analyze_tp_export import load_rows  # noqa: E402
from readiness_total_load import (  # noqa: E402
    compute_readiness_at,
    format_snapshot_markdown,
    load_config,
    parse_activity_points,
    parse_wellness_rows,
    resolve_as_of,
)


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def fetch_exports(days: int, data_dir: Path) -> tuple[Path, Path]:
    data_dir.mkdir(parents=True, exist_ok=True)
    wellness = data_dir / "wellness-report.csv"
    activities = data_dir / "activities-report.csv"
    _run(
        [
            sys.executable,
            str(_SCRIPT_DIR / "fetch_intervals_wellness.py"),
            "--days",
            str(days),
            "-o",
            str(wellness),
        ]
    )
    _run(
        [
            sys.executable,
            str(_SCRIPT_DIR / "fetch_intervals_activities.py"),
            "--days",
            str(max(days, 14)),
            "-o",
            str(activities),
        ]
    )
    return wellness, activities


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generer standard coach-rapport med TB-Score og grafer"
    )
    parser.add_argument(
        "--wellness",
        type=Path,
        help="wellness.csv (default: fetch eller data/intervals/exports/wellness-latest.csv)",
    )
    parser.add_argument(
        "--activities",
        type=Path,
        help="activities.csv (default: fetch eller data/intervals/exports/uke-okt.csv)",
    )
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Hent wellness + activities fra Intervals API",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=_REPO / "reports/coach",
    )
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()

    data_dir = _REPO / "data/intervals/exports"
    wellness = args.wellness
    activities = args.activities

    if args.fetch:
        try:
            wellness, activities = fetch_exports(args.days, data_dir)
        except subprocess.CalledProcessError:
            print("Fetch failed — sjekk INTERVALS_API", file=sys.stderr)
            return 1
    else:
        if not wellness:
            for cand in (
                data_dir / "wellness-latest.csv",
                data_dir / "wellness-60d.csv",
                data_dir / "wellness-recent.csv",
            ):
                if cand.is_file():
                    wellness = cand
                    break
        if not activities:
            for cand in (
                data_dir / "activities-latest.csv",
                data_dir / "uke-okt.csv",
                data_dir / "uke-21d.csv",
            ):
                if cand.is_file():
                    activities = cand
                    break

    if not wellness or not wellness.is_file():
        print("Mangler wellness CSV — bruk --fetch eller --wellness", file=sys.stderr)
        return 1
    if not activities or not activities.is_file():
        print("Mangler activities CSV — bruk --fetch eller --activities", file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y-%m-%d")
    out = args.output_dir / stamp
    out.mkdir(parents=True, exist_ok=True)

    cfg = load_config(args.config)
    w_rows, w_fields = load_rows(wellness)
    days = parse_wellness_rows(w_rows, w_fields)
    a_rows, a_fields = load_rows(activities)
    acts = parse_activity_points(a_rows, a_fields)
    as_of = resolve_as_of("now", cfg)
    snapshot = compute_readiness_at(as_of, days, acts, cfg, False)

    try:
        _run(
            [
                sys.executable,
                str(_SCRIPT_DIR / "analyze_intervals_wellness.py"),
                str(wellness),
            ]
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Wellness-analyse hoppet over: {exc}", file=sys.stderr)

    plots_ok = False
    try:
        _run(
            [
                sys.executable,
                str(_SCRIPT_DIR / "plot_readiness_report.py"),
                str(wellness),
                "--activities",
                str(activities),
                "-o",
                str(out),
                "--days",
                str(args.days),
            ]
        )
        plots_ok = True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Grafer hoppet over (matplotlib?): {exc}", file=sys.stderr)

    md_parts = [
        f"# Coach-rapport — {stamp}\n",
        f"**Kilde:** `{wellness.name}` + `{activities.name}`  \n",
        "**Totalbelastning:** TB-Score v2 (tidspunkt, subjektiv av)\n",
        format_snapshot_markdown(snapshot),
    ]
    if plots_ok:
        md_parts.extend(
            [
                "\n## Grafer\n",
                "| Graf | Fil |\n|------|-----|\n",
                f"| Dashboard | `{out.name}/tb-dashboard.png` |\n",
                f"| TB trend morgen/kveld | `{out.name}/tb-score-trend.png` |\n",
                f"| Komponenter nå | `{out.name}/tb-components-now.png` |\n",
                f"| TB nå | `{out.name}/tb-score-now.png` |\n",
            ]
        )
    else:
        md_parts.append(
            "\n## Grafer\n\n*(ikke generert — kjør `plot_readiness_report.py` lokalt)*\n"
        )
    md_parts.extend(
        [
            "\n## Rutine\n",
            "Agenten / appen skal kjøre dette scriptet ved **rapport / analyse / ukesopp** når data finnes.\n",
        ]
    )
    report_path = out / "coach-report.md"
    report_path.write_text("".join(md_parts), encoding="utf-8")
    latest_link = args.output_dir / "latest"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    latest_link.symlink_to(out.name)

    print(f"\nRapport: {report_path}")
    print(f"Grafer: {out}/")
    print(format_snapshot_markdown(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
