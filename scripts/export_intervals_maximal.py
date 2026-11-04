#!/usr/bin/env python3
"""Maximal Intervals.icu CSV export: wellness, activities, events, laps/intervals.

Requires INTERVALS_API or INTERVALS_API_KEY (and optional INTERVALS_ATHLETE_ID).
Never logs or writes the API key.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from intervals_lib import api_get, api_key, athlete_id  # noqa: E402

# Flattened interval columns (stable subset + extras discovered per row)
INTERVAL_CORE = [
    "activity_id",
    "activity_start",
    "activity_name",
    "activity_type",
    "interval_index",
    "id",
    "type",
    "label",
    "group_id",
    "start_index",
    "end_index",
    "start_time",
    "end_time",
    "moving_time",
    "elapsed_time",
    "distance",
    "average_watts",
    "weighted_average_watts",
    "max_watts",
    "average_watts_kg",
    "intensity",
    "training_load",
    "joules",
    "zone",
    "zone_min_watts",
    "zone_max_watts",
    "average_heartrate",
    "min_heartrate",
    "max_heartrate",
    "average_cadence",
    "min_cadence",
    "max_cadence",
    "average_speed",
    "min_speed",
    "max_speed",
    "average_torque",
    "total_elevation_gain",
    "average_gradient",
    "min_altitude",
    "max_altitude",
    "decoupling",
    "w5s_variability",
    "wbal_start",
    "wbal_end",
]

STREAM_SUMMARY_FIELDS = [
    "activity_id",
    "activity_start",
    "activity_name",
    "activity_type",
    "stream_rows",
    "stream_columns",
    "has_watts",
    "has_heartrate",
    "has_cadence",
    "has_velocity",
    "has_altitude",
    "duration_secs",
]


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _mask(s: str) -> str:
    if not s:
        return ""
    if len(s) <= 4:
        return "***"
    return s[:2] + "***" + s[-2:]


def write_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def fetch_csv(path: str, out: Path, *, timeout: int = 120) -> int:
    body = api_get(path, timeout=timeout)
    # strip BOM for cleaner git diffs
    if body.startswith(b"\xef\xbb\xbf"):
        body = body[3:]
    write_bytes(out, body)
    lines = body.count(b"\n")
    _log(f"Wrote {out} ({len(body)} bytes, ~{lines} lines)")
    return lines


def list_activities_json(oldest: str, newest: str) -> list[dict]:
    aid = athlete_id()
    body = api_get(
        f"/athlete/{aid}/activities?oldest={oldest}&newest={newest}",
        timeout=120,
    )
    data = json.loads(body)
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected activities payload: {type(data)}")
    return data


def activity_detail(activity_id: str) -> dict:
    return json.loads(api_get(f"/activity/{activity_id}?intervals=true", timeout=90))


def streams_summary(activity_id: str, meta: dict) -> dict | None:
    try:
        raw = api_get(f"/activity/{activity_id}/streams.csv", timeout=90)
    except Exception as e:  # noqa: BLE001 — continue on per-activity failures
        _log(f"streams skip {activity_id}: {type(e).__name__}")
        return None
    text = raw.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    if not lines:
        return None
    header = lines[0]
    cols = [c.strip().lower() for c in header.split(",")]
    n = max(0, len(lines) - 1)
    return {
        "activity_id": activity_id,
        "activity_start": meta.get("start_date_local") or meta.get("start_date") or "",
        "activity_name": meta.get("name") or "",
        "activity_type": meta.get("type") or "",
        "stream_rows": n,
        "stream_columns": "|".join(cols),
        "has_watts": int(any("watt" in c for c in cols)),
        "has_heartrate": int(any("heart" in c or c == "hr" for c in cols)),
        "has_cadence": int(any("cadence" in c for c in cols)),
        "has_velocity": int(any("veloc" in c or "speed" in c for c in cols)),
        "has_altitude": int(any("alt" in c for c in cols)),
        "duration_secs": n - 1 if n else 0,
    }


def flatten_intervals(act: dict, detail: dict) -> list[dict]:
    rows: list[dict] = []
    intervals = detail.get("icu_intervals") or []
    for i, iv in enumerate(intervals):
        row = {
            "activity_id": act.get("id") or detail.get("id") or "",
            "activity_start": act.get("start_date_local")
            or detail.get("start_date_local")
            or "",
            "activity_name": act.get("name") or detail.get("name") or "",
            "activity_type": act.get("type") or detail.get("type") or "",
            "interval_index": i,
        }
        for k in INTERVAL_CORE:
            if k in row:
                continue
            row[k] = iv.get(k, "")
        # keep a few extras if present
        for extra in ("gap", "strain_score", "joules_above_ftp"):
            if extra in iv and extra not in row:
                row[extra] = iv.get(extra)
        rows.append(row)
    return rows


def write_dicts_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    _log(f"Wrote {path} ({len(rows)} rows)")


def mirror_latest(src_dir: Path, latest: Path, names: list[str]) -> None:
    latest.mkdir(parents=True, exist_ok=True)
    for name in names:
        src = src_dir / name
        if not src.exists():
            continue
        dst = latest / name
        if dst.is_symlink() or dst.exists():
            dst.unlink()
        # copy (symlink may break across checkouts); also try relative symlink
        dst.write_bytes(src.read_bytes())
    # point latest/README to dated if present
    readme = src_dir / "README.md"
    if readme.is_file():
        (latest / "README.md").write_text(readme.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Maximal Intervals.icu CSV export")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default data/intervals/exports/YYYY-MM-DD)",
    )
    parser.add_argument("--wellness-days", type=int, default=365)
    parser.add_argument("--activities-days", type=int, default=180)
    parser.add_argument(
        "--laps-days",
        type=int,
        default=90,
        help="Full interval/lap detail for activities newer than this many days",
    )
    parser.add_argument(
        "--events-past-days",
        type=int,
        default=30,
        help="Planned/calendar events lookback",
    )
    parser.add_argument(
        "--events-forward-days",
        type=int,
        default=60,
        help="Planned/calendar events lookforward",
    )
    parser.add_argument(
        "--streams-summary-days",
        type=int,
        default=90,
        help="Per-activity streams.csv column/row summary for this window",
    )
    parser.add_argument("--sleep", type=float, default=0.15, help="Delay between detail GETs")
    parser.add_argument("--limit-laps", type=int, default=0, help="Debug: max activities for laps")
    args = parser.parse_args()

    if not api_key():
        _log("Set INTERVALS_API or INTERVALS_API_KEY")
        return 1

    today = date.today()
    stamp = today.isoformat()
    root = Path(__file__).resolve().parents[1]
    out_dir = args.out_dir or (root / "data" / "intervals" / "exports" / stamp)
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = root / "data" / "intervals" / "exports" / "latest"

    aid = athlete_id()
    _log(f"Export athlete={aid} key={_mask(api_key())} → {out_dir}")

    wel_oldest = (today - timedelta(days=max(args.wellness_days, 1) - 1)).isoformat()
    act_oldest = (today - timedelta(days=max(args.activities_days, 1) - 1)).isoformat()
    laps_oldest = (today - timedelta(days=max(args.laps_days, 1) - 1)).isoformat()
    streams_oldest = (
        today - timedelta(days=max(args.streams_summary_days, 1) - 1)
    ).isoformat()
    ev_oldest = (today - timedelta(days=max(args.events_past_days, 1) - 1)).isoformat()
    ev_newest = (today + timedelta(days=max(args.events_forward_days, 0))).isoformat()
    newest = today.isoformat()

    meta = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "athlete_id": aid,
        "wellness_range": [wel_oldest, newest],
        "activities_range": [act_oldest, newest],
        "laps_range": [laps_oldest, newest],
        "streams_summary_range": [streams_oldest, newest],
        "events_range": [ev_oldest, ev_newest],
        "gaps": [],
        "files": {},
    }

    # 1) Wellness CSV
    fetch_csv(
        f"/athlete/{aid}/wellness.csv?oldest={wel_oldest}&newest={newest}",
        out_dir / "wellness.csv",
    )
    meta["files"]["wellness.csv"] = "daily wellness (sleep, HRV, weight, CTL/ATL, …)"

    # 2) Activities CSV
    fetch_csv(
        f"/athlete/{aid}/activities.csv?oldest={act_oldest}&newest={newest}",
        out_dir / "activities.csv",
        timeout=180,
    )
    meta["files"]["activities.csv"] = "completed activities summary CSV"

    # Also JSON list for id iteration (same window as activities)
    acts = list_activities_json(act_oldest, newest)
    (out_dir / "activities.json").write_text(
        json.dumps(acts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    meta["files"]["activities.json"] = f"same range as activities.csv ({len(acts)} activities)"
    _log(f"activities.json: {len(acts)} activities")

    # 3) Events / planned workouts CSV + JSON
    fetch_csv(
        f"/athlete/{aid}/events.csv?oldest={ev_oldest}&newest={ev_newest}",
        out_dir / "events.csv",
    )
    meta["files"]["events.csv"] = "calendar events (WORKOUT/NOTE/TARGET/…)"
    events = json.loads(
        api_get(
            f"/athlete/{aid}/events?oldest={ev_oldest}&newest={ev_newest}",
            timeout=120,
        )
    )
    (out_dir / "events.json").write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    workouts = [e for e in events if (e.get("category") or "").upper() == "WORKOUT"]
    (out_dir / "events-workouts.json").write_text(
        json.dumps(workouts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    meta["files"]["events-workouts.json"] = f"WORKOUT events only ({len(workouts)})"

    # 4) Laps / intervals — full detail for laps window
    laps_cutoff = date.fromisoformat(laps_oldest)
    streams_cutoff = date.fromisoformat(streams_oldest)
    lap_rows: list[dict] = []
    stream_rows: list[dict] = []
    per_act_dir = out_dir / "laps"
    per_act_dir.mkdir(parents=True, exist_ok=True)

    acts_sorted = sorted(
        acts,
        key=lambda a: a.get("start_date_local") or "",
        reverse=True,
    )
    if args.limit_laps:
        acts_sorted = acts_sorted[: args.limit_laps]

    n_detail = 0
    n_skip_old = 0
    n_fail = 0
    for act in acts_sorted:
        aid_act = act.get("id")
        if not aid_act:
            continue
        start = (act.get("start_date_local") or "")[:10]
        try:
            start_d = date.fromisoformat(start) if start else None
        except ValueError:
            start_d = None

        want_laps = start_d is None or start_d >= laps_cutoff
        want_streams = start_d is None or start_d >= streams_cutoff
        if not want_laps and not want_streams:
            n_skip_old += 1
            continue

        try:
            if want_laps:
                detail = activity_detail(str(aid_act))
                rows = flatten_intervals(act, detail)
                lap_rows.extend(rows)
                # one CSV per activity (even if empty — documents no intervals)
                fields = list(INTERVAL_CORE) + ["gap", "strain_score", "joules_above_ftp"]
                write_dicts_csv(per_act_dir / f"{aid_act}.csv", fields, rows)
                n_detail += 1
            if want_streams:
                sm = streams_summary(str(aid_act), act)
                if sm:
                    stream_rows.append(sm)
        except Exception as e:  # noqa: BLE001
            n_fail += 1
            _log(f"detail fail {aid_act}: {type(e).__name__}: {str(e)[:160]}")
            meta["gaps"].append({"activity_id": aid_act, "error": type(e).__name__})
        time.sleep(max(args.sleep, 0.0))

    write_dicts_csv(
        out_dir / "laps.csv",
        list(INTERVAL_CORE) + ["gap", "strain_score", "joules_above_ftp"],
        lap_rows,
    )
    meta["files"]["laps.csv"] = (
        f"flattened icu_intervals for activities ≥ {laps_oldest} ({len(lap_rows)} rows)"
    )
    meta["files"]["laps/"] = f"one CSV per activity ({n_detail} files)"

    write_dicts_csv(out_dir / "streams-summary.csv", STREAM_SUMMARY_FIELDS, stream_rows)
    meta["files"]["streams-summary.csv"] = (
        f"streams.csv column/row presence ≥ {streams_oldest} ({len(stream_rows)} rows)"
    )

    meta["stats"] = {
        "activities_total": len(acts),
        "laps_activities_fetched": n_detail,
        "laps_rows": len(lap_rows),
        "streams_summaries": len(stream_rows),
        "skipped_older_than_laps_window": n_skip_old,
        "detail_failures": n_fail,
        "events_total": len(events),
        "events_workouts": len(workouts),
    }

    (out_dir / "export-meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    readme = f"""# Intervals.icu exports ({stamp})

Athlete: `{aid}` · exported: `{meta["exported_at"]}`

## Files

| File | Range | Contents |
|------|-------|----------|
| `wellness.csv` | {wel_oldest} … {newest} | Daily wellness (sleep, HRV, weight, readiness, CTL/ATL, …) |
| `activities.csv` | {act_oldest} … {newest} | Completed activities summary |
| `activities.json` | same | Same activities as JSON (ids for lap fetch) |
| `events.csv` | {ev_oldest} … {ev_newest} | Calendar events (WORKOUT / NOTE / TARGET / …) |
| `events.json` | same | Full event JSON |
| `events-workouts.json` | same | WORKOUT category only |
| `laps.csv` | activities ≥ {laps_oldest} | All `icu_intervals` rows (long form) |
| `laps/<activity_id>.csv` | same | One file per activity |
| `streams-summary.csv` | ≥ {streams_oldest} | Per-activity streams.csv shape (not full streams) |
| `export-meta.json` | — | Ranges, stats, gaps |

## Laps schema (`laps.csv` / `laps/*.csv`)

From `GET /api/v1/activity/{{id}}?intervals=true` → `icu_intervals[]`.

Key columns: `activity_id`, `interval_index`, `type` (WORK/REST/…), `label`, `start_time`/`end_time` (s), `moving_time`, `distance`, power (`average_watts`, `weighted_average_watts`, `intensity`, `zone`), HR, cadence, speed, `training_load`.

## Refresh

```bash
export INTERVALS_ATHLETE_ID={aid}
export INTERVALS_API_KEY=…   # or INTERVALS_API
python3 scripts/export_intervals_maximal.py
# optional: --wellness-days 365 --activities-days 180 --laps-days 90
```

Then copy key files into `data/intervals/exports/latest/` (the script does this).

Context pack (uses newest CSVs under exports/):

```bash
python3 scripts/build_context_pack.py --days 14
# or with live fetch: python3 scripts/build_context_pack.py --fetch-icu --days 14
```

## Gaps / notes

- Full second-by-second `streams.csv` is **not** committed (size); only `streams-summary.csv`.
- Interval detail limited to last **{args.laps_days}** days; older activities appear in `activities.csv` only.
- Detail failures: {n_fail} (see `export-meta.json` → `gaps`).
- Do not commit API keys.
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")
    # also top-level exports README pointer
    exports_readme = root / "data" / "intervals" / "exports" / "README.md"
    exports_readme.write_text(
        f"""# Intervals.icu CSV exports

Latest full dump: **`{stamp}/`** (also mirrored in `latest/`).

See `{stamp}/README.md` for schema, ranges, and refresh commands.

```bash
export INTERVALS_ATHLETE_ID={aid}
export INTERVALS_API_KEY=…   # never commit
python3 scripts/export_intervals_maximal.py
```
""",
        encoding="utf-8",
    )

    mirror_names = [
        "wellness.csv",
        "activities.csv",
        "activities.json",
        "events.csv",
        "events.json",
        "events-workouts.json",
        "laps.csv",
        "streams-summary.csv",
        "export-meta.json",
        "README.md",
    ]
    mirror_latest(out_dir, latest, mirror_names)
    # Per-activity laps/ stay only under dated folder (latest keeps aggregated laps.csv).

    _log(
        f"Done. acts={len(acts)} lap_rows={len(lap_rows)} "
        f"streams={len(stream_rows)} events={len(events)} workouts={len(workouts)}"
    )
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
