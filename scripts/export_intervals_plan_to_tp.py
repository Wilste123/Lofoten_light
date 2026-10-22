#!/usr/bin/env python3
"""Export planned Intervals.icu calendar workouts to TP-importable files."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO = _SCRIPT_DIR.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from intervals_lib import api_get  # noqa: E402
from zwo_common import esc, write_zwo_power  # noqa: E402

WORKOUT_TYPES = {"Ride", "Run", "Swim", "WeightTraining"}


def slug(s: str, max_len: int = 60) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[-\s]+", "-", s.strip()).strip("-")
    return (s[:max_len] or "workout").lower()


def flatten_steps(steps: list, out: list[tuple[int, str, float]]) -> None:
    """Bike: (duration_sec, label, power_fraction)."""
    for step in steps or []:
        if step.get("reps") and step.get("steps"):
            reps = int(step.get("reps") or 1)
            for _ in range(reps):
                flatten_steps(step["steps"], out)
            continue
        dur = int(step.get("duration") or 0)
        if dur <= 0:
            continue
        text = (step.get("text") or "Step").strip()
        power = step.get("power") or {}
        units = (power.get("units") or "").lower()
        val = power.get("value")
        if val is None and isinstance(power.get("start"), (int, float)):
            val = (float(power["start"]) + float(power.get("end", power["start"]))) / 2
        if units == "%ftp" and val is not None:
            out.append((dur, text, float(val) / 100.0))
        elif step.get("hr"):
            # fallback: map mid HR % LTHR to rough power for ZWO placeholder
            hr = step["hr"]
            mid = (float(hr.get("start", 85)) + float(hr.get("end", 85))) / 2
            out.append((dur, f"{text} (~{mid:.0f}% LTHR)", min(max(mid / 100.0, 0.5), 1.15)))


def format_steps_text(steps: list, indent: int = 0) -> list[str]:
    lines: list[str] = []
    pad = "  " * indent
    for step in steps or []:
        if step.get("reps") and step.get("steps"):
            lines.append(f"{pad}{step.get('text', 'Repeat')} x{step['reps']}")
            lines.extend(format_steps_text(step["steps"], indent + 1))
            continue
        dur = int(step.get("duration") or 0)
        text = step.get("text") or "Step"
        extra = ""
        if step.get("power"):
            p = step["power"]
            extra = f" power {p.get('value')}{p.get('units', '')}"
        if step.get("hr"):
            h = step["hr"]
            extra = f" HR {h.get('start')}-{h.get('end')}{h.get('units', '')}"
        if step.get("pace"):
            pc = step["pace"]
            extra = f" pace {pc.get('start')}-{pc.get('end')}{pc.get('units', '')}"
        lines.append(f"{pad}- {dur // 60}:{dur % 60:02d} {text}{extra}")
    return lines


def event_to_files(
    event: dict, out_dir: Path, repo_root: Path
) -> dict[str, str] | None:
    cat = event.get("category") or ""
    if cat in ("TARGET",):
        return None
    typ = event.get("type") or ""
    if typ not in WORKOUT_TYPES:
        return None
    name = (event.get("name") or "Workout").strip()
    date = (event.get("start_date_local") or "")[:10]
    if not date:
        return None
    eid = event.get("id")
    base = f"{date}_{slug(name)}_{eid}"
    desc = (event.get("description") or "").strip()
    load = event.get("icu_training_load")
    moving = event.get("moving_time")

    sport_folder = {
        "Ride": "bike",
        "Run": "run",
        "Swim": "swim",
        "WeightTraining": "strength",
    }[typ]

    result: dict[str, str] = {
        "date": date,
        "type": typ,
        "name": name,
        "load": str(load or ""),
        "duration_sec": str(moving or ""),
    }

    wd = event.get("workout_doc")
    steps = (wd or {}).get("steps") if isinstance(wd, dict) else None

    if typ == "Ride" and steps:
        flat: list[tuple[int, str, float]] = []
        flatten_steps(steps, flat)
        if flat:
            zwo_path = out_dir / "bike" / f"{base}.zwo"
            write_zwo_power(
                zwo_path,
                "bike",
                f"{date} — {name}",
                desc.split("\n")[0][:120] if desc else name,
                [(d, t, p, None) for d, t, p in flat],
                "Eksport fra Intervals.icu → TP bibliotek (FTP 210 W i TP).",
                tp_library_import=True,
            )
            result["file"] = str(zwo_path.relative_to(out_dir))
            return result

    # Run / swim / strength / bike without structure: text bundle for TP calendar notes + builder
    txt_path = out_dir / sport_folder / f"{base}.txt"
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    body = [
        f"# {name}",
        f"Date: {date}",
        f"Sport: {typ}",
        f"Planned load (Intervals): {load or '—'}",
        f"Duration (s): {moving or '—'}",
        "",
    ]
    if desc:
        body.append("## Description (from Intervals)")
        body.append(desc)
        body.append("")
    if steps:
        body.append("## Structure")
        body.extend(format_steps_text(steps))
        body.append("")
    body.append("## TrainingPeaks")
    body.append(
        "- Sykkel med .zwo i bike/: importer til bibliotek, dra til kalender på dato."
    )
    body.append(
        "- Løp/svøm/styrke: bruk Workout Builder (HR/pace) eller lim inn struktur over."
    )
    txt_path.write_text("\n".join(body), encoding="utf-8")
    result["file"] = str(txt_path.relative_to(out_dir))
    return result


def fetch_events(oldest: str, newest: str) -> list[dict]:
    raw = api_get(
        f"/athlete/0/events?oldest={oldest}&newest={newest}",
        timeout=180,
    )
    return json.loads(raw.decode())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start",
        default="2026-11-01",
        help="First calendar day (ISO)",
    )
    parser.add_argument(
        "--end",
        default="2027-04-30",
        help="Last calendar day (ISO)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_REPO / "exports" / "tp-from-intervals",
    )
    args = parser.parse_args()

    events = fetch_events(args.start, args.end)
    events.sort(key=lambda e: e.get("start_date_local") or "")

    out_dir = args.output
    out_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("bike", "run", "swim", "strength"):
        (out_dir / sub).mkdir(exist_ok=True)

    rows: list[dict[str, str]] = []
    zwo_n = 0
    txt_n = 0
    for ev in events:
        row = event_to_files(ev, out_dir, _REPO)
        if row:
            rows.append(row)
            if row["file"].endswith(".zwo"):
                zwo_n += 1
            else:
                txt_n += 1

    index_path = out_dir / "index.csv"
    if rows:
        with index_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["date", "type", "name", "load", "duration_sec", "file"],
            )
            w.writeheader()
            w.writerows(rows)

    readme = out_dir / "README-TP-import.md"
    readme.write_text(
        f"""# Intervals → TrainingPeaks export

Generated from Intervals.icu calendar **{args.start}** … **{args.end}** (planned workouts only).

| Count | |
|-------|---|
| Bike `.zwo` | {zwo_n} |
| Run/swim/strength `.txt` | {txt_n} |
| Index | `index.csv` |

## Sykkel (TP Virtual / rulla)

1. TrainingPeaks → **Library** → Import **`.zwo`** from `bike/`.
2. Dra økt til **kalender** på riktig dato (se `index.csv`).
3. FTP **210 W** i TP soner.

## Løp / svøm / styrke

- TP importerer ikke struktur fra `.txt` automatisk.
- Åpne filen → bygg i **Workout Builder** (HR / % threshold pace / CSS), eller lim beskrivelse i kalender-notat.
- `index.csv` har dato, navn og planlagt load fra Intervals.

Kjør på nytt etter endringer i Intervals:

```bash
python3 scripts/export_intervals_plan_to_tp.py --start 2026-09-01 --end 2026-10-31 -o exports/tp-from-intervals
```
""",
        encoding="utf-8",
    )

    print(f"Exported {len(rows)} workouts to {out_dir}")
    print(f"  ZWO: {zwo_n}, TXT: {txt_n}")
    print(f"  {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
