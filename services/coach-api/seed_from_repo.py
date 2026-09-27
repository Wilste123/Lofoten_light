"""Import William (or fixture athlete docs) into coach-web SQLite + profile.md.

Assumptions (documented for operators):
- Årsmål 750–800 t → midtpunkt **775 t** for season_* targets.
- Disiplin-fordeling fra plans/2026-2027-12mnd-periodisering.md:
  sykkel 50 %, løp 30 %, svøm 16 %, styrke rest (~4 %).
- goal_race_date = 2027-08-20 (Lofoten Half Extreme — se docs/product/progress-compliance.md).
- season_start_date = 2026-09-28 (planstart B0).
- Historisk FTP 410 W er IKKE seedet som ftp_tested; bruk 210 W fra soner-planlegging.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

# Allow `python scripts/seed_william_from_repo.py` and `python -m` from coach-api
_API_DIR = Path(__file__).resolve().parent
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

import config
from db import (
    db_session,
    get_athlete,
    get_plan_block,
    init_db,
    insert_athlete,
    insert_plan_block,
    list_plan_blocks,
    update_athlete,
    update_plan_block,
)

SEED_ATHLETE_ID = "william-lofoten"
SEED_USERNAME = "william"
DEFAULT_DISPLAY_NAME = "William"
# Product onboarding default is Rocky; William-seed prefers Ole (OPV-stemme).
DEFAULT_COACH_NAME = "Ole"
GOAL_RACE_DATE = "2027-08-20"
SEASON_START = "2026-09-28"
# 775 h mid of 750–800; % from periodisering snitt år
SEASON_TOTAL_H = 775.0
SEASON_BIKE_H = round(SEASON_TOTAL_H * 0.50)  # 388 → 388
SEASON_RUN_H = round(SEASON_TOTAL_H * 0.30)  # 232
SEASON_SWIM_H = round(SEASON_TOTAL_H * 0.16)  # 124
SEASON_STRENGTH_H = round(
    SEASON_TOTAL_H - SEASON_BIKE_H - SEASON_RUN_H - SEASON_SWIM_H
)  # ~31

# B0–B10 from plans/blokker-periodisering-2026-2027.md (explicit ranges / gantt)
PLAN_BLOCKS: list[dict[str, Any]] = [
    {
        "key": "b0",
        "title": "B0 — Startblokk",
        "theme": "Re-etablering · kontakt alle tre ben",
        "start_date": "2026-09-28",
        "end_date": "2026-10-25",
        "weekly_hours": 6.5,
        "sort_order": 0,
    },
    {
        "key": "b1",
        "title": "B1 — Kontakt II",
        "theme": "Re-etablering · stabilisere 12 økter/14 dager",
        "start_date": "2026-10-26",
        "end_date": "2026-11-22",
        "weekly_hours": 8.5,
        "sort_order": 1,
    },
    {
        "key": "b2",
        "title": "B2 — Mot 10 t",
        "theme": "Re-etablering → base",
        "start_date": "2026-11-23",
        "end_date": "2026-12-20",
        "weekly_hours": 9.5,
        "sort_order": 2,
    },
    {
        "key": "b3",
        "title": "B3 — Aerob bred",
        "theme": "Base tidlig",
        "start_date": "2026-12-21",
        "end_date": "2027-02-14",
        "weekly_hours": 10.5,
        "sort_order": 3,
    },
    {
        "key": "b4",
        "title": "B4 — Vinter solid",
        "theme": "Base",
        "start_date": "2027-02-15",
        "end_date": "2027-04-11",
        "weekly_hours": 12.0,
        "sort_order": 4,
    },
    {
        "key": "b5",
        "title": "B5 — Base peak",
        "theme": "Base → build bro",
        "start_date": "2027-04-12",
        "end_date": "2027-05-09",
        "weekly_hours": 13.5,
        "sort_order": 5,
    },
    {
        "key": "b6",
        "title": "B6 — Build 1",
        "theme": "Kvalitet",
        "start_date": "2027-05-10",
        "end_date": "2027-06-20",
        "weekly_hours": 14.5,
        "sort_order": 6,
    },
    {
        "key": "b7",
        "title": "B7 — Build 2",
        "theme": "Brick og OWS",
        "start_date": "2027-06-21",
        "end_date": "2027-07-18",
        "weekly_hours": 15.0,
        "sort_order": 7,
    },
    {
        "key": "b8",
        "title": "B8 — Build 3",
        "theme": "Volum topp",
        "start_date": "2027-07-19",
        "end_date": "2027-08-01",
        "weekly_hours": 15.5,
        "sort_order": 8,
    },
    {
        "key": "b9",
        "title": "B9 — Spesifikk",
        "theme": "Half Extreme prep",
        "start_date": "2027-08-02",
        "end_date": "2027-08-15",
        "weekly_hours": 15.0,
        "sort_order": 9,
    },
    {
        "key": "b10",
        "title": "B10 — Taper + race",
        "theme": "Race",
        "start_date": "2027-08-16",
        "end_date": "2027-08-22",
        "weekly_hours": 8.0,
        "sort_order": 10,
    },
]

DEFAULT_AGREEMENTS = [
    "Hovedmål: fullføre Lofoten Half Extreme 2027 (cut-offs) — ikke Norseman/full Extreme nå",
    "Prioritering: kontinuitet → skadefrihet → gradvis progresjon → aerob → Lofoten → prestasjon",
    "Historisk FTP 410 W (2019) er ikke intensitetsgrunnlag; bruk konservativ nå-FTP til re-test",
    "Årsmål 750–800 t (rullerende 12 mnd) — ikke 2019-volum (~20 t/uke) før MSK tåler det",
    "Svøm er limiter: ikke bytt bort basseng til ekstra sykkel",
    "Rygg/isjasnerven: stopp ved økt prikking/nerve-trekk fra rygg; ingen hero markløft/RDL tidlig",
    "Race-vekt under 80 kg — avbryt aggressiv vektnedgang hvis FTP eller styrke faller",
    "Hver uke har Plan B; recovery hver 3.–4. uke",
    "TP/Intervals: kommenter økter; søndag ukesopp",
]


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _first_table_value(md: str, label: str) -> str | None:
    """Pull a markdown table cell value by left-column label (fuzzy)."""
    for line in md.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        if label.lower() in cells[0].lower():
            val = re.sub(r"\*+", "", cells[1]).strip()
            val = re.sub(r"`([^`]+)`", r"\1", val)
            return val or None
    return None


def _extract_ftp(soner_md: str, profile_md: str) -> tuple[float | None, str | None]:
    for src in (soner_md, profile_md):
        m = re.search(r"FTP[^\n]*?\*\*?(\d{2,3})\s*W", src, re.I)
        if m:
            return float(m.group(1)), "2026-09-24"
        m = re.search(r"\|\s*FTP sykkel\s*\|\s*\*\*?(\d{2,3})", src, re.I)
        if m:
            return float(m.group(1)), "2026-09-24"
    # Prefer 210 over 410
    for src in (soner_md, profile_md):
        if "210" in src and "FTP" in src:
            return 210.0, "2026-09-24"
    return None, None


def _extract_weight_age(profile_md: str) -> tuple[float | None, int | None]:
    weight = None
    age = None
    m = re.search(r"~?\*?\*?(9\d)\s*kg", profile_md, re.I)
    if m:
        weight = float(m.group(1))
    m = re.search(r"Mann,\s*(\d{2})\s*år", profile_md, re.I)
    if m:
        age = int(m.group(1))
    return weight, age


def _extract_goal_text(goals_md: str) -> str:
    if not goals_md:
        return (
            "Lofoten Half Extreme 2027 — fullføre (cut-offs); "
            "styringsanker ca. 6:30–7:00; race-vekt under 80 kg"
        )
    # Compact summary from goals header table
    race = _first_table_value(goals_md, "Arrangement") or "Lofoten Half Extreme 2027"
    goal_type = _first_table_value(goals_md, "Måltype") or "fullføre"
    weight = _first_table_value(goals_md, "Race-vekt") or "under 80 kg"
    # Strip markdown bold remnants
    for raw in (race, goal_type, weight):
        pass
    lines = [
        f"{race.strip('* ')}",
        f"Mål: {goal_type[:180]}",
        f"Race-vekt: {weight[:120]}",
        "Volum: 750–800 t / 12 mnd. Ikke Norseman/full Extreme nå.",
    ]
    return "\n".join(lines)


def _extract_injuries(plager_md: str, profile_md: str) -> str:
    if plager_md:
        # Keep coach rules, trim file links noise
        body = plager_md
        if len(body) > 2200:
            body = body[:2200] + "\n\n[…trimmet i seed…]"
        return body
    return "Se docs/athlete/plager-rygg-isjas.md (rygg / isjasnerven / ankel)."


def _extract_schedule(profile_md: str) -> str:
    planstart = _first_table_value(profile_md, "Planstart") or "28.09.2026"
    days = _first_table_value(profile_md, "Treningsdager") or "7/7 med recovery-uke"
    indoor = _first_table_value(profile_md, "Innendørs / utendørs") or "Trondheim"
    return (
        f"Planstart: {planstart}. Treningsdager: {days}. "
        f"Oppsett: {indoor}. Basseng 3T vinter; smart rulle nov 2026."
    )


def _extract_weekly_focus(uke_notater: str) -> str:
    if not uke_notater:
        return "B0: kontakt alle tre ben — 3× svøm, Z2 sykkel, løp RPE≤5, styrke 2×"
    m = re.search(
        r"\*\*Tema:\*\*\s*(.+)",
        uke_notater,
    )
    tema = m.group(1).strip() if m else "Kontakt alle tre ben"
    return f"B0 nåværende: {tema} · 3× svøm non-negotiable · Plan B aktiv"


def _extract_agreements(extra_md: str = "") -> list[str]:
    found: list[str] = []
    # Bullets under ## Avtaler if present in any source
    for chunk in (extra_md,):
        in_section = False
        for line in chunk.splitlines():
            if re.match(r"^##\s+Avtaler", line, re.I):
                in_section = True
                continue
            if in_section and line.startswith("## "):
                break
            if in_section:
                m = re.match(r"^[-*]\s+(.+)", line.strip())
                if m:
                    found.append(m.group(1).strip())
    # Merge defaults; keep order, unique
    out: list[str] = []
    for a in found + DEFAULT_AGREEMENTS:
        if a and a not in out:
            out.append(a)
    return out


def _coach_from_treneridentitet(knowledge_coach: Path, fallback: str) -> tuple[str, str]:
    """Return (display_name, personality). Title rarely has a short name → fallback."""
    path = knowledge_coach / "treneridentitet.md"
    text = _read(path)
    # No explicit app display name in title — OPV voice
    if "Ole Petter" in text or "Ole Petter" in text[:500]:
        return fallback, "opv"
    return fallback, "opv"


def compose_rich_profile_md(
    *,
    athlete: dict[str, Any],
    profile_src: str,
    goals_src: str,
    plager_src: str,
    soner_src: str,
) -> str:
    """Rich runtime profile mirroring repo athlete docs (not the thin onboarding template)."""
    name = athlete.get("display_name") or "William"
    coach = athlete.get("coach_display_name") or DEFAULT_COACH_NAME
    agreements = athlete.get("agreements") or []
    agr = "\n".join(f"- {a}" for a in agreements) if agreements else "- (ingen)"

    # Trim huge sources for prompt budget
    def trim(s: str, n: int = 3500) -> str:
        s = s.strip()
        return s if len(s) <= n else s[: n - 20] + "\n\n[…trimmet…]"

    return f"""# Athlete profile — {name}

Importert fra git `docs/athlete/` via `seed_from_repo` (speil — slett ikke kilden i repo).
Oppdateres ved re-seed; Du-fanen kan overskrive med generisk mal (kjør seed på nytt for full speiling).

## App-kontekst

| | |
|---|---|
| Visningsnavn | {name} |
| Trener | {coach} ({athlete.get("coach_personality") or "opv"}) |
| Sport | {athlete.get("sport") or "triathlon"} |
| Tidssone | {athlete.get("timezone") or "Europe/Oslo"} |
| Alder | {athlete.get("age_years") or "—"} |
| Vekt (kg) | {athlete.get("weight_kg") or "—"} |
| Testet FTP | {athlete.get("ftp_tested") or "—"} W ({athlete.get("ftp_tested_at") or ""}) |
| Sesongstart | {athlete.get("season_start_date") or SEASON_START} |
| Race-dato | {athlete.get("goal_race_date") or GOAL_RACE_DATE} |
| Sesongmål (t) | svøm {athlete.get("season_swim_hours_target")} · sykkel {athlete.get("season_bike_hours_target")} · løp {athlete.get("season_run_hours_target")} · styrke {athlete.get("season_strength_hours_target")} |

## Mål (kort)

{athlete.get("goal_text") or "(ikke satt)"}

## Ukens fokus

{athlete.get("weekly_focus") or "(ikke satt)"}

## Tilgjengelighet

{athlete.get("schedule_notes") or "(ikke satt)"}

## Avtaler

{agr}

## Begrensninger / skade

{athlete.get("injury_notes") or "(ingen)"}

## Notater

{athlete.get("notes") or "(ingen)"}

---

## Speil: docs/athlete/profile.md

{trim(profile_src, 4000)}

## Speil: docs/athlete/goals.md

{trim(goals_src, 2500)}

## Speil: docs/athlete/plager-rygg-isjas.md

{trim(plager_src, 2000)}

## Speil: docs/athlete/soner-planlegging-2026.md

{trim(soner_src, 1200)}

## Coaching notes (for agenten)

- Tilpass råd til **{name}** — historikk (FTP 410, NTG) står her; ikke anta den for andre utøvere.
- Trenerstemme: **{coach}**, personlighet «{athlete.get("coach_personality") or "opv"}».
- Intervals eier øktdetaljer; denne filen eier menneskelig kontekst og avtaler.
- Ikke dump hele `knowledge/` — kun trimmet knowledge_ctx + denne profilen.
"""


def build_athlete_payload(
    *,
    repo_root: Path,
    athlete_docs: Path,
    plans_dir: Path,
    display_name: str,
    coach_name: str,
    athlete_id: str,
) -> dict[str, Any]:
    profile_src = _read(athlete_docs / "profile.md")
    goals_src = _read(athlete_docs / "goals.md")
    plager_src = _read(athlete_docs / "plager-rygg-isjas.md")
    soner_src = _read(athlete_docs / "soner-planlegging-2026.md")
    uke0 = _read(plans_dir / "uke-notater" / "2026-09-28-blokk-4uker.md")

    ftp, ftp_at = _extract_ftp(soner_src, profile_src)
    weight, age = _extract_weight_age(profile_src)
    coach, personality = _coach_from_treneridentitet(
        repo_root / "knowledge" / "coach", coach_name
    )

    agreements = _extract_agreements(profile_src + "\n" + goals_src)
    notes_parts = [
        "Seedet fra lofoten_light docs/athlete + plans/blokker-periodisering.",
        "ZWO-bibliotek og full knowledge/ forblir i git — ikke i DB.",
    ]
    kropp = _read(athlete_docs / "kroppssammensetning-smartvekt.md")
    if kropp:
        notes_parts.append(
            "Kroppssammensetning: race <80 kg; BIA morgen snitt — se docs/athlete/kroppssammensetning-smartvekt.md"
        )

    return {
        "id": athlete_id,
        "username": SEED_USERNAME if athlete_id == SEED_ATHLETE_ID else None,
        "display_name": display_name,
        "timezone": "Europe/Oslo",
        "coach_display_name": coach,
        "coach_personality": personality,
        "coach_style_note": (
            "Ole Petter Vibekken-inspirert: struktur, krav, ærlig risiko — tilpasset tri/comeback"
        ),
        "accent_color": "#1a6b4a",
        "goal_text": _extract_goal_text(goals_src),
        "injury_notes": _extract_injuries(plager_src, profile_src),
        "agreements": agreements,
        "weekly_focus": _extract_weekly_focus(uke0),
        "ftp_tested": ftp,
        "ftp_tested_at": ftp_at,
        "weight_kg": weight,
        "age_years": age,
        "sport": "triathlon",
        "schedule_notes": _extract_schedule(profile_src),
        "nutrition_ibs": "no",
        "nutrition_gluten": "none",
        "nutrition_lactose": False,
        "nutrition_notes": "",
        "notes": "\n".join(notes_parts),
        "season_swim_hours_target": float(SEASON_SWIM_H),
        "season_bike_hours_target": float(SEASON_BIKE_H),
        "season_run_hours_target": float(SEASON_RUN_H),
        "season_strength_hours_target": float(SEASON_STRENGTH_H),
        "season_start_date": SEASON_START,
        "goal_race_date": GOAL_RACE_DATE,
        "setup_completed": True,
        "_sources": {
            "profile": profile_src,
            "goals": goals_src,
            "plager": plager_src,
            "soner": soner_src,
        },
    }


def resolve_athlete_id(conn, seed_id: str, display_name: str) -> tuple[str, bool]:
    """Return (athlete_id, created). Prefer fixed seed id, else display_name match."""
    if get_athlete(conn, seed_id):
        return seed_id, False
    cur = conn.execute(
        "SELECT id FROM athletes WHERE lower(display_name) = lower(?) LIMIT 1",
        (display_name,),
    )
    row = cur.fetchone()
    if row:
        return row["id"], False
    return seed_id, True


def upsert_plan_blocks(conn, athlete_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in PLAN_BLOCKS:
        block_id = f"{athlete_id}-{spec['key']}"
        data = {
            "id": block_id,
            "title": spec["title"],
            "theme": spec["theme"],
            "start_date": spec["start_date"],
            "end_date": spec["end_date"],
            "weekly_hours": spec["weekly_hours"],
            "sort_order": spec["sort_order"],
        }
        existing = get_plan_block(conn, athlete_id, block_id)
        if existing:
            patch = {k: data[k] for k in (
                "title", "theme", "start_date", "end_date", "weekly_hours", "sort_order"
            )}
            block = update_plan_block(conn, athlete_id, block_id, patch)
        else:
            block = insert_plan_block(conn, athlete_id, data)
        out.append(block)
    return out


def seed_athlete(
    *,
    repo_root: Path | None = None,
    athlete_docs: Path | None = None,
    plans_dir: Path | None = None,
    db_path: Path | None = None,
    athletes_dir: Path | None = None,
    display_name: str = DEFAULT_DISPLAY_NAME,
    coach_name: str = DEFAULT_COACH_NAME,
    seed_id: str = SEED_ATHLETE_ID,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create/update athlete, plan_blocks, and rich profile.md. Idempotent."""
    root = repo_root or config.REPO_ROOT
    docs = athlete_docs or (root / "docs" / "athlete")
    plans = plans_dir or (root / "plans")
    database = db_path or config.DATABASE_PATH
    out_athletes = athletes_dir or config.ATHLETES_DATA_DIR

    payload = build_athlete_payload(
        repo_root=root,
        athlete_docs=docs,
        plans_dir=plans,
        display_name=display_name,
        coach_name=coach_name,
        athlete_id=seed_id,
    )
    sources = payload.pop("_sources")

    if dry_run:
        return {
            "dry_run": True,
            "athlete_id": seed_id,
            "display_name": display_name,
            "goal_text": payload["goal_text"],
            "ftp_tested": payload.get("ftp_tested"),
            "agreements_count": len(payload["agreements"]),
            "plan_blocks": len(PLAN_BLOCKS),
            "season_hours": {
                "swim": payload["season_swim_hours_target"],
                "bike": payload["season_bike_hours_target"],
                "run": payload["season_run_hours_target"],
                "strength": payload["season_strength_hours_target"],
            },
            "goal_race_date": payload["goal_race_date"],
            "profile_would_include": bool(sources["profile"]),
        }

    init_db(database)
    out_athletes.mkdir(parents=True, exist_ok=True)

    with db_session(database) as conn:
        athlete_id, created = resolve_athlete_id(conn, seed_id, display_name)
        payload["id"] = athlete_id
        if created:
            athlete = insert_athlete(conn, payload)
            # season_* + goal_race not in INSERT — patch immediately
            athlete = update_athlete(
                conn,
                athlete_id,
                {
                    "season_swim_hours_target": payload["season_swim_hours_target"],
                    "season_bike_hours_target": payload["season_bike_hours_target"],
                    "season_run_hours_target": payload["season_run_hours_target"],
                    "season_strength_hours_target": payload["season_strength_hours_target"],
                    "season_start_date": payload["season_start_date"],
                    "goal_race_date": payload["goal_race_date"],
                    "agreements": payload["agreements"],
                    "injury_notes": payload["injury_notes"],
                    "goal_text": payload["goal_text"],
                    "weekly_focus": payload["weekly_focus"],
                    "schedule_notes": payload["schedule_notes"],
                    "notes": payload["notes"],
                    "ftp_tested": payload.get("ftp_tested"),
                    "ftp_tested_at": payload.get("ftp_tested_at"),
                    "weight_kg": payload.get("weight_kg"),
                    "age_years": payload.get("age_years"),
                    "coach_display_name": payload["coach_display_name"],
                    "coach_personality": payload["coach_personality"],
                    "coach_style_note": payload["coach_style_note"],
                    "setup_completed": True,
                },
            )
            blocks = upsert_plan_blocks(conn, athlete_id)
            preserved = False
        else:
            existing = get_athlete(conn, athlete_id)
            # Already through setup (seeded William or confirmed user): never wipe
            # goals / plan_blocks / profile / Intervals secrets on re-seed / boot.
            if existing and bool(existing.get("setup_completed")):
                ensure: dict[str, Any] = {"setup_completed": True}
                if payload.get("username") and not existing.get("username"):
                    ensure["username"] = payload["username"]
                elif (
                    athlete_id == SEED_ATHLETE_ID
                    and existing.get("username") != SEED_USERNAME
                ):
                    # Keep preferred seed username if free / already william
                    if existing.get("username") in (None, "", SEED_USERNAME):
                        ensure["username"] = SEED_USERNAME
                athlete = update_athlete(conn, athlete_id, ensure) or existing
                blocks = list_plan_blocks(conn, athlete_id)
                preserved = True
            else:
                athlete = update_athlete(conn, athlete_id, {
                    k: payload[k]
                    for k in (
                        "username",
                        "display_name",
                        "timezone",
                        "coach_display_name",
                        "coach_personality",
                        "coach_style_note",
                        "accent_color",
                        "goal_text",
                        "injury_notes",
                        "agreements",
                        "weekly_focus",
                        "ftp_tested",
                        "ftp_tested_at",
                        "weight_kg",
                        "age_years",
                        "sport",
                        "schedule_notes",
                        "notes",
                        "season_swim_hours_target",
                        "season_bike_hours_target",
                        "season_run_hours_target",
                        "season_strength_hours_target",
                        "season_start_date",
                        "goal_race_date",
                        "setup_completed",
                    )
                    if k != "username" or payload.get("username")
                })
                blocks = upsert_plan_blocks(conn, athlete_id)
                preserved = False

    assert athlete is not None
    dest = out_athletes / athlete_id
    dest.mkdir(parents=True, exist_ok=True)
    profile_path = dest / "profile.md"

    if preserved and profile_path.is_file():
        # Keep runtime profile.md (and never touch athlete_secrets)
        pass
    else:
        rich = compose_rich_profile_md(
            athlete=athlete,
            profile_src=sources["profile"],
            goals_src=sources["goals"],
            plager_src=sources["plager"],
            soner_src=sources["soner"],
        )
        profile_path.write_text(rich, encoding="utf-8")

    return {
        "dry_run": False,
        "created": created,
        "preserved": preserved,
        "athlete_id": athlete_id,
        "display_name": athlete["display_name"],
        "coach_display_name": athlete["coach_display_name"],
        "setup_completed": bool(athlete.get("setup_completed")),
        "goal_text": athlete.get("goal_text"),
        "goal_race_date": athlete.get("goal_race_date"),
        "ftp_tested": athlete.get("ftp_tested"),
        "agreements": athlete.get("agreements"),
        "plan_blocks": len(blocks),
        "profile_path": str(profile_path),
        "invite_hint": (
            f"Sett X-Athlete-Id={athlete_id} (eller lim inn i app-session). "
            f"Bootstrap: POST /v1/session/bootstrap {{\"athlete_id\": \"{athlete_id}\"}}"
        ),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Seed William from docs/athlete + plans into coach-web SQLite. "
            f"Season targets assume {SEASON_TOTAL_H:.0f} h/year "
            f"(bike {SEASON_BIKE_H}, run {SEASON_RUN_H}, swim {SEASON_SWIM_H}, "
            f"strength {SEASON_STRENGTH_H}) from periodisering %-fordeling. "
            f"Race date default {GOAL_RACE_DATE}."
        )
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repo root (default: coach-api config.REPO_ROOT)",
    )
    p.add_argument(
        "--athlete-docs",
        type=Path,
        default=None,
        help="Override docs/athlete path (tests/fixtures)",
    )
    p.add_argument(
        "--plans-dir",
        type=Path,
        default=None,
        help="Override plans/ path",
    )
    p.add_argument("--db", type=Path, default=None, help="SQLite path")
    p.add_argument(
        "--athletes-dir",
        type=Path,
        default=None,
        help="data/athletes output dir",
    )
    p.add_argument("--display-name", default=DEFAULT_DISPLAY_NAME)
    p.add_argument(
        "--coach-name",
        default=DEFAULT_COACH_NAME,
        help="App coach display name (default Ole; product onboarding default is Rocky)",
    )
    p.add_argument("--seed-id", default=SEED_ATHLETE_ID)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse sources and print summary without writing DB/files",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = seed_athlete(
        repo_root=args.repo_root,
        athlete_docs=args.athlete_docs,
        plans_dir=args.plans_dir,
        db_path=args.db,
        athletes_dir=args.athletes_dir,
        display_name=args.display_name,
        coach_name=args.coach_name,
        seed_id=args.seed_id,
        dry_run=args.dry_run,
    )
    print("--- seed_from_repo ---")
    for k, v in result.items():
        if k == "agreements" and isinstance(v, list):
            print(f"agreements ({len(v)}):")
            for a in v:
                print(f"  - {a}")
        else:
            print(f"{k}: {v}")
    if not result.get("dry_run"):
        print()
        print(f"athlete_id={result['athlete_id']}")
        print(result.get("invite_hint", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
