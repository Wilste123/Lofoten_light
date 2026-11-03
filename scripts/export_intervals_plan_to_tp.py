#!/usr/bin/env python3
"""Export planned Intervals.icu calendar workouts to TP-importable files."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO = _SCRIPT_DIR.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from intervals_lib import api_get  # noqa: E402
from zwo_common import RUN_NOTE, SWIM_NOTE, write_zwo_power  # noqa: E402

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
            hr = step["hr"]
            mid = (float(hr.get("start", 85)) + float(hr.get("end", 85))) / 2
            out.append((dur, f"{text} (~{mid:.0f}% LTHR)", min(max(mid / 100.0, 0.5), 1.15)))
        elif step.get("pace"):
            pc = step["pace"]
            start = float(pc.get("start", 100))
            end = float(pc.get("end", start))
            mid = (start + end) / 2
            out.append((dur, text, min(max(mid / 100.0, 0.5), 1.2)))
        else:
            out.append((dur, text, 0.78))


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


def day_number(plan_start: str, workout_date: str) -> int:
    return (date.fromisoformat(workout_date) - date.fromisoformat(plan_start)).days + 1


def strength_dojo_row(event: dict, plan_start: str) -> dict[str, str]:
    name = (event.get("name") or "Styrke").strip()
    wdate = (event.get("start_date_local") or "")[:10]
    moving = int(event.get("moving_time") or 0)
    dur_min = max(1, round(moving / 60)) if moving else 35
    load = event.get("icu_training_load")
    desc = (event.get("description") or "").strip()
    wd = event.get("workout_doc")
    steps = (wd or {}).get("steps") if isinstance(wd, dict) else None
    if steps:
        struct = "\n".join(format_steps_text(steps))
        desc = f"{desc}\n\n{struct}".strip() if desc else struct
    if not desc:
        desc = f"Fra Intervals.icu ({wdate})"
    desc = desc.replace("\r\n", "\n").replace("\n", " ").strip()
    return {
        "day": str(day_number(plan_start, wdate)),
        "sport": "Strength",
        "subtype": "general",
        "title": name,
        "duration_minutes": str(dur_min),
        "tss": str(int(load)) if load else "15",
        "description": desc[:8000],
        "phase": "export",
    }


def write_structured_zwo(
    typ: str,
    out_dir: Path,
    base: str,
    date: str,
    name: str,
    desc: str,
    steps: list | None,
    moving: int | None,
) -> Path | None:
    flat: list[tuple[int, str, float]] = []
    flatten_steps(steps, flat)
    if not flat and moving and int(moving) > 0:
        flat = [(int(moving), name, 0.78)]
    if not flat:
        return None

    folder = {"Ride": "bike", "Run": "run", "Swim": "swim"}[typ]
    zwo_path = out_dir / folder / f"{base}.zwo"
    if typ == "Ride":
        zwo_name = f"{date} — {name}"
        note = "Eksport Intervals → TP bibliotek (sett sykkel-FTP i TP)."
    elif typ == "Run":
        zwo_name = f"LØP {date} — {name}"
        note = RUN_NOTE
    else:
        zwo_name = f"SVØM {date} — {name}"
        note = SWIM_NOTE

    write_zwo_power(
        zwo_path,
        "bike",
        zwo_name,
        desc.split("\n")[0][:120] if desc else name,
        [(d, t, p, None) for d, t, p in flat],
        note,
        tp_library_import=True,
    )
    return zwo_path


def event_to_files(
    event: dict,
    out_dir: Path,
    plan_start: str,
) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    cat = event.get("category") or ""
    if cat in ("TARGET",):
        return None, None
    typ = event.get("type") or ""
    if typ not in WORKOUT_TYPES:
        return None, None
    name = (event.get("name") or "Workout").strip()
    date = (event.get("start_date_local") or "")[:10]
    if not date:
        return None, None
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

    if typ == "WeightTraining":
        result["file"] = "trainingdojo-import.csv"
        result["format"] = "trainingdojo"
        return result, strength_dojo_row(event, plan_start)

    mov = int(moving) if moving else None
    if typ in ("Ride", "Run", "Swim"):
        zwo_path = write_structured_zwo(typ, out_dir, base, date, name, desc, steps, mov)
        if zwo_path:
            result["file"] = str(zwo_path.relative_to(out_dir))
            result["format"] = "zwo"
            return result, None

    txt_path = out_dir / sport_folder / f"{base}.txt"
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    body = [
        f"# {name}",
        f"Date: {date}",
        f"Sport: {typ}",
        f"Planned load (Intervals): {load or '—'}",
        f"Duration (s): {moving or '—'}",
        "",
        "Ingen struktur i Intervals — bygg manuelt i TP eller legg til steg i Intervals og kjør export på nytt.",
    ]
    if desc:
        body.extend(["", desc])
    txt_path.write_text("\n".join(body), encoding="utf-8")
    result["file"] = str(txt_path.relative_to(out_dir))
    result["format"] = "txt-fallback"
    return result, None


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
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("bike", "run", "swim", "strength"):
        (out_dir / sub).mkdir(exist_ok=True)

    rows: list[dict[str, str]] = []
    dojo_rows: list[dict[str, str]] = []
    zwo_n = 0
    txt_n = 0
    for ev in events:
        row, dojo = event_to_files(ev, out_dir, args.start)
        if row:
            rows.append(row)
            fmt = row.get("format", "")
            if fmt == "zwo":
                zwo_n += 1
            elif fmt == "txt-fallback":
                txt_n += 1
        if dojo:
            dojo_rows.append(dojo)

    if dojo_rows:
        dojo_path = out_dir / "trainingdojo-import.csv"
        fields = [
            "day",
            "sport",
            "subtype",
            "title",
            "duration_minutes",
            "tss",
            "description",
            "phase",
        ]
        with dojo_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(dojo_rows)

    index_path = out_dir / "index.csv"
    if rows:
        with index_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "date",
                    "type",
                    "name",
                    "load",
                    "duration_sec",
                    "format",
                    "file",
                ],
            )
            w.writeheader()
            w.writerows(rows)

    readme = out_dir / "README-TP-import.md"
    readme.write_text(
        f"""# Intervals → TrainingPeaks export

Kalender **{args.start}** … **{args.end}** (planlagte økter fra Intervals.icu).

| | Antall |
|---|--:|
| `.zwo` (sykkel + løp + svøm) | {zwo_n} |
| Styrke (TrainingDojo CSV) | {len(dojo_rows)} |
| Tekst-fallback (mangler struktur) | {txt_n} |

## Hvorfor bare ZWO i TP?

TrainingPeaks **Library → Import** godtar kun **kraftbasert sykkel** `.zwo` ([TP Help](https://help.trainingpeaks.com/hc/en-us/articles/32432105650573-Import-Planned-Workouts-into-TrainingPeaks)). Ingen filimport for planlagt løp/svøm/styrke.

**Løsning i denne pakken**

1. **Sykkel** — `bike/*.zwo` → importer → dra på kalender (FTP i TP).
2. **Løp/svøm** — `run/` og `swim/` er **sykkel-format ZWO** med prefiks LØP/SVØM (samme triks som i repo: `docs/trainingpeaks/importer-lop-svom-zwo.md`):
   - Importer `.zwo` som sykkel
   - Åpne økt → **Build** → sport **Run** / **Swim** → intensitet **% threshold pace**
   - Lagre → dra på kalender
3. **Styrke** — ingen ZWO. Bruk **`trainingdojo-import.csv`** på [trainingdojo.app/import](https://trainingdojo.app/import), plan start **`{args.start}`**.

## Kjør på nytt

```bash
python3 scripts/export_intervals_plan_to_tp.py --start {args.start} --end {args.end} -o exports/tp-from-intervals
```
""",
        encoding="utf-8",
    )

    print(f"Exported {len(rows)} workouts to {out_dir}")
    print(f"  ZWO: {zwo_n}, strength (dojo): {len(dojo_rows)}, txt fallback: {txt_n}")
    print(f"  {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
