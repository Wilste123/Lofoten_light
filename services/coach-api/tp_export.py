"""Intervals planned calendar → TrainingPeaks import zip (no TP write API).

Same idea as ``scripts/export_intervals_plan_to_tp.py``: ZWO (bike + run/swim as
bike-format) + TrainingDojo CSV for strength. Soft-fails without Intervals.
Never writes to Intervals or TrainingPeaks.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

WORKOUT_TYPES = {"Ride", "Run", "Swim", "WeightTraining"}

RUN_NOTE = (
    "IMPORT: TP godtar kun sykkel-ZWO — filen er sportType=bike for import. "
    "Etter import: åpne økt → Bygg → sett sport til Løp → intensitet % terskel-pace."
)
SWIM_NOTE = (
    "IMPORT: TP godtar kun sykkel-ZWO — filen er sportType=bike for import. "
    "Etter import: åpne økt → Bygg → sett sport til Svøm → intensitet % T-pace."
)
BIKE_NOTE = "Eksport Intervals → TP bibliotek (sett sykkel-FTP i TP)."


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def slug(s: str, max_len: int = 60) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[-\s]+", "-", s.strip()).strip("-")
    return (s[:max_len] or "workout").lower()


def day_number(plan_start: str, workout_date: str) -> int:
    return (date.fromisoformat(workout_date) - date.fromisoformat(plan_start)).days + 1


def flatten_steps(steps: list, out: list[tuple[int, str, float]]) -> None:
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


def zwo_bytes(
    *,
    name: str,
    description: str,
    steps: list[tuple[int, str, float]],
    note: str,
) -> bytes:
    desc = f"{description} — {note}" if description else note
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<workout_file>",
        "  <author>Lofoten coach</author>",
        f"  <name>{_esc(name)}</name>",
        f"  <description>{_esc(desc)}</description>",
        "  <sportType>bike</sportType>",
        "  <tags/>",
        "  <workout>",
    ]
    for dur, msg, power in steps:
        p = max(float(power), 0.45)
        lines.append(f'    <SteadyState Duration="{int(dur)}" Power="{p:.4f}" pace="0">')
        lines.append(f'      <textevent message="{_esc(msg)}" timeoffset="0"/>')
        lines.append("    </SteadyState>")
    lines.extend(["  </workout>", "</workout_file>", ""])
    return "\n".join(lines).encode("utf-8")


def strength_dojo_row(event: dict[str, Any], plan_start: str) -> dict[str, str]:
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


def event_files(
    event: dict[str, Any],
    plan_start: str,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    """Return (index_row with optional file_bytes/path, optional dojo_row)."""
    cat = event.get("category") or ""
    if cat in ("TARGET",):
        return None, None
    typ = event.get("type") or ""
    if typ not in WORKOUT_TYPES:
        return None, None
    name = (event.get("name") or "Workout").strip()
    wdate = (event.get("start_date_local") or "")[:10]
    if not wdate:
        return None, None
    eid = event.get("id")
    base = f"{wdate}_{slug(name)}_{eid}"
    desc = (event.get("description") or "").strip()
    load = event.get("icu_training_load")
    moving = event.get("moving_time")
    wd = event.get("workout_doc")
    steps = (wd or {}).get("steps") if isinstance(wd, dict) else None

    result: dict[str, Any] = {
        "date": wdate,
        "type": typ,
        "name": name,
        "load": str(load or ""),
        "duration_sec": str(moving or ""),
    }

    if typ == "WeightTraining":
        result["file"] = "trainingdojo-import.csv"
        result["format"] = "trainingdojo"
        return result, strength_dojo_row(event, plan_start)

    flat: list[tuple[int, str, float]] = []
    flatten_steps(steps or [], flat)
    if not flat and moving and int(moving) > 0:
        flat = [(int(moving), name, 0.78)]

    folder = {"Ride": "bike", "Run": "run", "Swim": "swim"}[typ]
    if flat:
        if typ == "Ride":
            zwo_name = f"{wdate} — {name}"
            note = BIKE_NOTE
        elif typ == "Run":
            zwo_name = f"LØP {wdate} — {name}"
            note = RUN_NOTE
        else:
            zwo_name = f"SVØM {wdate} — {name}"
            note = SWIM_NOTE
        rel = f"{folder}/{base}.zwo"
        result["file"] = rel
        result["format"] = "zwo"
        result["file_bytes"] = zwo_bytes(
            name=zwo_name,
            description=desc.split("\n")[0][:120] if desc else name,
            steps=flat,
            note=note,
        )
        return result, None

    # Text fallback — no structure
    body = [
        f"# {name}",
        f"Date: {wdate}",
        f"Sport: {typ}",
        f"Planned load (Intervals): {load or '—'}",
        f"Duration (s): {moving or '—'}",
        "",
        "Ingen struktur i Intervals — bygg manuelt i TP.",
    ]
    if desc:
        body.extend(["", desc])
    rel = f"{folder}/{base}.txt"
    result["file"] = rel
    result["format"] = "txt-fallback"
    result["file_bytes"] = "\n".join(body).encode("utf-8")
    return result, None


def build_tp_export_zip(
    events: list[dict[str, Any]],
    *,
    start: str,
    end: str,
) -> tuple[bytes, dict[str, Any]]:
    """Build zip bytes + summary meta. No network, no TP write."""
    rows: list[dict[str, Any]] = []
    dojo_rows: list[dict[str, str]] = []
    zwo_n = 0
    txt_n = 0
    file_payloads: list[tuple[str, bytes]] = []

    for ev in sorted(events or [], key=lambda e: e.get("start_date_local") or ""):
        row, dojo = event_files(ev, start)
        if row:
            fmt = row.get("format") or ""
            if fmt == "zwo":
                zwo_n += 1
            elif fmt == "txt-fallback":
                txt_n += 1
            blob = row.pop("file_bytes", None)
            if blob and row.get("file") and fmt != "trainingdojo":
                file_payloads.append((str(row["file"]), blob))
            rows.append(row)
        if dojo:
            dojo_rows.append(dojo)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, blob in file_payloads:
            zf.writestr(rel, blob)
        if dojo_rows:
            dojo_buf = io.StringIO()
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
            w = csv.DictWriter(dojo_buf, fieldnames=fields)
            w.writeheader()
            w.writerows(dojo_rows)
            zf.writestr("trainingdojo-import.csv", dojo_buf.getvalue().encode("utf-8"))
        if rows:
            idx = io.StringIO()
            fields = [
                "date",
                "type",
                "name",
                "load",
                "duration_sec",
                "format",
                "file",
            ]
            w = csv.DictWriter(idx, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
            zf.writestr("index.csv", idx.getvalue().encode("utf-8"))
        readme = f"""# Intervals → TrainingPeaks export

Kalender **{start}** … **{end}** (planlagte økter fra Intervals.icu).

| | Antall |
|---|--:|
| `.zwo` (sykkel + løp + svøm) | {zwo_n} |
| Styrke (TrainingDojo CSV) | {len(dojo_rows)} |
| Tekst-fallback | {txt_n} |

## Import

1. **Sykkel** — `bike/*.zwo` → TP Library → Import → dra på kalender.
2. **Løp/svøm** — `run/` / `swim/` er sykkel-format ZWO (LØP/SVØM-prefiks):
   importer → Build → bytt sport → % threshold pace.
3. **Styrke** — `trainingdojo-import.csv` på trainingdojo.app/import (plan start `{start}`).

Ingen auto-write til TrainingPeaks. Appen lager bare filer.

CLI: `python3 scripts/export_intervals_plan_to_tp.py --start {start} --end {end}`
"""
        zf.writestr("README-TP-import.md", readme.encode("utf-8"))

    meta = {
        "start": start,
        "end": end,
        "workouts": len(rows),
        "zwo": zwo_n,
        "strength": len(dojo_rows),
        "txt_fallback": txt_n,
        "written_to_trainingpeaks": False,
        "written_to_intervals": False,
        "filename": f"tp-from-intervals-{start}_{end}.zip",
    }
    return buf.getvalue(), meta


def default_export_range(*, today: date | None = None) -> tuple[str, str]:
    """This week Monday → +13 days (two weeks ahead of Monday)."""
    today = today or date.today()
    mon = today - timedelta(days=today.weekday())
    end = mon + timedelta(days=13)
    return mon.isoformat(), end.isoformat()


def export_tp_zip_for_athlete(
    secrets: dict[str, Any] | None,
    *,
    start: str | None = None,
    end: str | None = None,
    today: date | None = None,
) -> tuple[bytes | None, dict[str, Any]]:
    """Fetch ICU events and build zip. Soft empty when not linked."""
    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    aid = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    if not start or not end:
        start, end = default_export_range(today=today)
    if not key or not aid:
        return None, {
            "available": False,
            "start": start,
            "end": end,
            "note": "Intervals ikke koblet — kan ikke eksportere plan til TP-filer.",
            "written_to_trainingpeaks": False,
            "written_to_intervals": False,
        }
    try:
        from intervals_calendar import fetch_events

        events = fetch_events(key, aid, start, end)
    except Exception as exc:  # noqa: BLE001
        return None, {
            "available": False,
            "start": start,
            "end": end,
            "note": f"Intervals-henting feilet: {exc.__class__.__name__}",
            "written_to_trainingpeaks": False,
            "written_to_intervals": False,
        }
    blob, meta = build_tp_export_zip(events, start=start, end=end)
    meta["available"] = True
    meta["events_fetched"] = len(events)
    return blob, meta


def write_export_dir(
    events: list[dict[str, Any]],
    out_dir: Path,
    *,
    start: str,
    end: str,
) -> dict[str, Any]:
    """Disk write helper (tests / CLI parity)."""
    blob, meta = build_tp_export_zip(events, start=start, end=end)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / meta["filename"]
    zip_path.write_bytes(blob)
    meta["zip_path"] = str(zip_path)
    return meta
