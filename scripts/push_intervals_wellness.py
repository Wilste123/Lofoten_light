#!/usr/bin/env python3
"""Push BIA / body-composition rows from CSV to Intervals.icu wellness."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from intervals_lib import api_key, put_wellness, put_wellness_bulk  # noqa: E402

DAILY_COLUMNS = {
    "date": "date",
    "weight_kg": "weight",
    "body_fat_pct": "bodyFat",
    "resting_hr": "restingHR",
}

OPTIONAL_BIA = (
    "body_water_pct",
    "ffm_kg",
    "muscle_kg",
    "visceral",
    "bone_kg",
)


def _float(val: str | None) -> float | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    return float(s.replace(",", "."))


def build_bia_comment(row: dict[str, str], extra: str = "") -> str:
    parts: list[str] = []
    for key, label in (
        ("body_water_pct", "water"),
        ("ffm_kg", "ffm"),
        ("muscle_kg", "muscle"),
        ("visceral", "vis"),
        ("bone_kg", "bone"),
    ):
        v = _float(row.get(key))
        if v is not None:
            unit = "%" if key == "body_water_pct" else "kg" if "kg" in key else ""
            parts.append(f"{label}={v:g}{unit}")
    prefix = "BIA " + " ".join(parts) if parts else ""
    user = (row.get("comment") or row.get("comments") or extra or "").strip()
    if prefix and user:
        return f"{prefix} | {user}"
    return prefix or user


def row_to_wellness(row: dict[str, str], date_key: str = "date") -> dict:
    day = (row.get(date_key) or row.get("week_ending") or "").strip()
    if not day:
        raise ValueError("missing date")
    payload: dict = {"id": day}
    w = _float(row.get("weight_kg") or row.get("weight_kg_7d_avg"))
    if w is not None:
        payload["weight"] = round(w, 2)
    bf = _float(row.get("body_fat_pct") or row.get("body_fat_pct_7d_avg"))
    if bf is not None:
        payload["bodyFat"] = round(bf, 2)
    rhr = _float(row.get("resting_hr") or row.get("resting_hr_7d_avg"))
    if rhr is not None:
        payload["restingHR"] = int(round(rhr))
    comment = build_bia_comment(
        row,
        extra=(row.get("opv_line") or row.get("opv_note") or "").strip(),
    )
    if comment:
        payload["comments"] = comment[:2000]
    return payload


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main() -> int:
    parser = argparse.ArgumentParser(description="Push BIA CSV to Intervals wellness")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument(
        "--weekly",
        action="store_true",
        help="Use week_ending as wellness date (Sunday 7d averages)",
    )
    parser.add_argument(
        "--bulk",
        action="store_true",
        help="Use wellness-bulk endpoint (default: one PUT per row)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not api_key():
        print("Set INTERVALS_API or INTERVALS_API_KEY.", file=sys.stderr)
        return 1

    rows = load_csv(args.csv_path)
    if not rows:
        print("CSV is empty.", file=sys.stderr)
        return 1

    payloads: list[dict] = []
    for row in rows:
        d0 = (row.get("date") or row.get("week_ending") or "").strip()
        if not d0 or d0.startswith("#"):
            continue
        if args.weekly:
            row = dict(row)
            if row.get("week_ending"):
                row["date"] = row["week_ending"]
        try:
            payloads.append(row_to_wellness(row))
        except ValueError as e:
            print(f"Skip row: {e}", file=sys.stderr)

    if not payloads:
        print("No valid rows.", file=sys.stderr)
        return 1

    print(f"Prepared {len(payloads)} wellness update(s)")
    for p in payloads[:5]:
        print(f"  {p.get('id')}: weight={p.get('weight')} bodyFat={p.get('bodyFat')}")
    if len(payloads) > 5:
        print(f"  ... +{len(payloads) - 5} more")

    if args.dry_run:
        return 0

    if args.bulk:
        put_wellness_bulk(payloads)
        print("Bulk wellness push OK")
    else:
        for p in payloads:
            day = p.pop("id")
            put_wellness(day, p)
        print("Per-day wellness push OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
