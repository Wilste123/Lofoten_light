"""Adaptive setup: knowledge-grounded chat + plan preview.

Architecture (thin):
- Setup chat: one LLM call with adaptive knowledge chunks.
- Plan preview: one LLM call → JSON plan_blocks; validated/normalized in Python.
- No Pondus / tool-loop. Persist + Intervals only after explicit confirm.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from chat_service import call_llm
from knowledge_ctx import (
    detect_athlete_signals,
    knowledge_selection_meta,
    load_knowledge_bundle,
)

_PLAN_JSON_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE
)
_EXTRACT_JSON_RE = re.compile(
    r"```(?:json\s+)?setup_extract\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None


def _monday_on_or_after(d: date) -> date:
    return d if d.weekday() == 0 else d + timedelta(days=(7 - d.weekday()) % 7)


def default_season_window(
    *,
    season_start: str | None = None,
    goal_race: str | None = None,
    today: date | None = None,
    signals: dict[str, bool] | None = None,
) -> tuple[date, date]:
    today = today or date.today()
    start = _parse_date(season_start) or _monday_on_or_after(today)
    race = _parse_date(goal_race)
    signals = signals or {}
    if not race or race <= start:
        # Beginners: shorter first season horizon; returning: longer build
        weeks = 24 if signals.get("beginner") else 40 if signals.get("returning") else 32
        if signals.get("time_constrained"):
            weeks = min(weeks, 28)
        race = start + timedelta(weeks=weeks)
    return start, race


def estimate_weekly_hours(
    raw: Any,
    schedule_notes: str = "",
    signals: dict[str, bool] | None = None,
) -> float:
    signals = signals or {}
    try:
        if raw is not None and str(raw).strip() != "":
            v = float(raw)
            if 1.5 <= v <= 30.0:
                return round(v, 1)
    except (TypeError, ValueError):
        pass
    text = (schedule_notes or "").lower()
    m = re.search(r"(\d{1,2}(?:[.,]\d)?)\s*(?:t|timer|hours?)\s*(?:/|per)?\s*uke", text)
    if m:
        try:
            v = float(m.group(1).replace(",", "."))
            if 1.5 <= v <= 30.0:
                return round(v, 1)
        except ValueError:
            pass
    if signals.get("beginner"):
        return 5.0
    if signals.get("time_constrained"):
        return 6.0
    if signals.get("injury"):
        return 6.5
    if signals.get("returning"):
        return 8.0
    return 8.0


def _split_for_signals(signals: dict[str, bool]) -> dict[str, float]:
    if signals.get("beginner") and not signals.get("multisport"):
        # Single-sport lean until they declare triathlon
        return {"swim": 0.10, "bike": 0.35, "run": 0.45, "strength": 0.10}
    return {"swim": 0.16, "bike": 0.50, "run": 0.30, "strength": 0.04}


def season_targets_from_hours(
    weekly_hours: float,
    start: date,
    race: date,
    signals: dict[str, bool] | None = None,
) -> dict[str, float]:
    signals = signals or {}
    split = _split_for_signals(signals)
    weeks = max(1, (race - start).days / 7.0)
    annual = weekly_hours * weeks * 0.90
    return {
        "season_swim_hours_target": round(annual * split["swim"], 0),
        "season_bike_hours_target": round(annual * split["bike"], 0),
        "season_run_hours_target": round(annual * split["run"], 0),
        "season_strength_hours_target": round(annual * split["strength"], 0),
        "season_total_hours_est": round(annual, 0),
    }


def _fallback_blocks(
    *,
    season_start: date,
    goal_race: date,
    weekly_hours: float,
    signals: dict[str, bool],
    goal_text: str = "",
    injury_notes: str = "",
) -> list[dict[str, Any]]:
    """Adaptive fallback when LLM unavailable — still signal-aware, not one template."""
    if goal_race <= season_start:
        goal_race = season_start + timedelta(weeks=16)
    total_days = max(28, (goal_race - season_start).days)
    end_plan = goal_race - timedelta(days=1)

    if signals.get("beginner"):
        templates = [
            ("grunnlag", "Grunnlag", "etablering", "Vaner · teknikk · lav intensitet", 0.25, 0.75),
            ("base", "Base", "base", "Aerob kontinuitet", 0.35, 0.95),
            ("utvikling", "Utvikling", "build", "Lett kvalitet når stabil", 0.25, 1.05),
            ("målblokk", "Mot mål", "peak", "Spesifikk rolig oppbygging", 0.10, 1.0),
            ("taper", "Nedtrapping", "taper", "Frisk til start / milesten", 0.05, 0.70),
        ]
    elif signals.get("injury"):
        templates = [
            ("rehab", "Rehab / skånsom", "etablering", "Belastningsstyring · ACWR-trygg", 0.20, 0.60),
            ("rebuild", "Rebuild", "base", "Gradvis volum · styrke", 0.30, 0.85),
            ("base", "Base", "base", "Aerob base uten forcering", 0.25, 1.0),
            ("build", "Build", "build", "Kvalitet når smertefri", 0.15, 1.05),
            ("taper", "Buffer / taper", "taper", "Margin før mål", 0.10, 0.75),
        ]
    elif signals.get("returning"):
        templates = [
            ("kontakt", "Re-etablering", "etablering", "Kontakt alle ben · ikke 2019-watt", 0.15, 0.70),
            ("base1", "Base 1", "base", "Aerob · teknikk", 0.25, 0.90),
            ("base2", "Base 2", "base", "Volum opp kontrollert", 0.25, 1.05),
            ("build", "Build", "build", "Kvalitet / spesifikk", 0.20, 1.15),
            ("peak", "Peak", "peak", "Race-spesifikk", 0.10, 1.05),
            ("taper", "Taper", "taper", "Nedtrapping", 0.05, 0.65),
        ]
    elif signals.get("time_constrained"):
        templates = [
            ("vaner", "Vaner", "etablering", "Få økter · høy konsistens", 0.20, 0.85),
            ("base", "Base (effektiv)", "base", "Z2 + én Q/uke", 0.40, 1.0),
            ("build", "Build (kort)", "build", "Spesifikk uten volum-jakt", 0.30, 1.05),
            ("taper", "Taper", "taper", "Skarphet", 0.10, 0.70),
        ]
    else:
        templates = [
            ("start", "Start", "etablering", "Kartlegging · vaner", 0.15, 0.80),
            ("base", "Base", "base", "Aerob base", 0.35, 1.0),
            ("build", "Build", "build", "Kvalitet", 0.30, 1.10),
            ("peak", "Peak", "peak", "Spesifikk", 0.12, 1.05),
            ("taper", "Taper", "taper", "Nedtrapping", 0.08, 0.70),
        ]

    injury_bit = " · skånsom progresjon" if (injury_notes or "").strip() or signals.get("injury") else ""
    blocks: list[dict[str, Any]] = []
    cursor = season_start
    for i, (key, title, phase, theme, share, factor) in enumerate(templates):
        if i == len(templates) - 1:
            block_end = end_plan
        else:
            span = max(7, int(round(total_days * share)))
            block_end = min(end_plan, cursor + timedelta(days=span - 1))
        if block_end < cursor:
            block_end = cursor + timedelta(days=6)
        wh = round(weekly_hours * factor, 1)
        t = theme + injury_bit
        if goal_text and phase in ("build", "peak"):
            t = f"{theme} · mot {(goal_text.strip().split(chr(10))[0])[:60]}{injury_bit}"
        blocks.append(
            {
                "key": key,
                "title": title,
                "theme": t,
                "phase": phase,
                "start_date": cursor.isoformat(),
                "end_date": block_end.isoformat(),
                "weekly_hours": wh,
                "sort_order": i,
            }
        )
        cursor = block_end + timedelta(days=1)
        if cursor > end_plan:
            break
    return blocks


def normalize_plan_blocks(
    raw_blocks: list[Any],
    *,
    season_start: date,
    goal_race: date,
    weekly_hours: float,
    signals: dict[str, bool],
) -> list[dict[str, Any]]:
    """Validate LLM blocks into persistable plan_blocks; fall back if unusable."""
    cleaned: list[dict[str, Any]] = []
    for i, b in enumerate(raw_blocks or []):
        if not isinstance(b, dict):
            continue
        title = str(b.get("title") or "").strip()[:80]
        start = _parse_date(str(b.get("start_date") or ""))
        end = _parse_date(str(b.get("end_date") or ""))
        if not title or not start or not end or end < start:
            continue
        try:
            wh = float(b.get("weekly_hours")) if b.get("weekly_hours") is not None else weekly_hours
        except (TypeError, ValueError):
            wh = weekly_hours
        wh = max(1.5, min(30.0, round(wh, 1)))
        cleaned.append(
            {
                "key": str(b.get("key") or f"b{i}")[:32],
                "title": title,
                "theme": str(b.get("theme") or "").strip()[:160],
                "phase": str(b.get("phase") or "").strip()[:32],
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "weekly_hours": wh,
                "sort_order": int(b.get("sort_order") if b.get("sort_order") is not None else i),
            }
        )
    if len(cleaned) < 2:
        return _fallback_blocks(
            season_start=season_start,
            goal_race=goal_race,
            weekly_hours=weekly_hours,
            signals=signals,
        )
    cleaned.sort(key=lambda x: (x["start_date"], x["sort_order"]))
    for i, b in enumerate(cleaned):
        b["sort_order"] = i
    return cleaned


def build_overview_nb(
    *,
    blocks: list[dict[str, Any]],
    season_start: date,
    goal_race: date,
    weekly_hours: float,
    targets: dict[str, Any],
    goal_text: str = "",
    display_name: str = "",
    signals: dict[str, bool] | None = None,
    athlete_archetype: str = "",
    coach_note: str | None = None,
) -> str:
    name = (display_name or "du").strip() or "du"
    goal = (goal_text or "").strip() or "sesongmålet"
    signals = signals or {}
    arch = athlete_archetype or _archetype_label(signals)
    lines = [
        f"Grovplan for {name}",
        f"Profiltype (heuristikk): {arch}",
        "",
        f"Mål: {goal}",
        f"Sesongvindu: {season_start.isoformat()} → {goal_race.isoformat()}",
        f"Typisk ukelast: ca. {weekly_hours} t (justeres per blokk).",
        (
            f"Est. sesongvolum: ~{int(targets.get('season_total_hours_est') or 0)} t "
            f"(svøm {int(targets.get('season_swim_hours_target') or 0)} / "
            f"sykkel {int(targets.get('season_bike_hours_target') or 0)} / "
            f"løp {int(targets.get('season_run_hours_target') or 0)} / "
            f"styrke {int(targets.get('season_strength_hours_target') or 0)})."
        ),
        "",
        "Periodisering (meso-blokker):",
    ]
    for b in blocks:
        lines.append(
            f"- **{b['title']}** ({b['start_date']}–{b['end_date']}): "
            f"{b['theme']} · {b['weekly_hours']} t/uke"
        )
    lines.extend(
        [
            "",
            "Treningsplan-outline: appen eier makro/meso. "
            "Dagsøkter/ZWO lever i Intervals. Etter bekreftelse kan grovplan "
            "speiles som ukenoter (`ll-coach-…`) — ikke fulle økter.",
            "",
            "Ingenting er lagret eller synct før du bekrefter.",
        ]
    )
    if coach_note:
        lines.extend(["", "Trenerens kommentar:", coach_note.strip()])
    return "\n".join(lines)


def _archetype_label(signals: dict[str, bool]) -> str:
    tags = []
    if signals.get("beginner"):
        tags.append("nybegynner")
    if signals.get("returning"):
        tags.append("comeback/erfaren")
    if signals.get("injury"):
        tags.append("skade/rehab")
    if signals.get("time_constrained"):
        tags.append("tidsklemma")
    if signals.get("multisport"):
        tags.append("flersport")
    return ", ".join(tags) if tags else "generell utholdenhet"


def _parse_json_object(reply: str) -> dict[str, Any] | None:
    if not reply:
        return None
    m = _PLAN_JSON_RE.search(reply)
    raw = m.group(1) if m else reply.strip()
    # Try direct / fence; also find first {…}
    for candidate in (raw, reply[reply.find("{") : reply.rfind("}") + 1] if "{" in reply else ""):
        if not candidate or "{" not in candidate:
            continue
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def generate_plan_with_llm(
    draft: dict[str, Any],
    *,
    knowledge_dir,
    api_key: str,
    model: str,
    signals: dict[str, bool],
    season_start: date,
    goal_race: date,
    weekly_hours: float,
) -> tuple[list[dict[str, Any]], str | None, str]:
    """One LLM pass → blocks + coach_note. Returns (blocks, note, source)."""
    if not api_key:
        return (
            _fallback_blocks(
                season_start=season_start,
                goal_race=goal_race,
                weekly_hours=weekly_hours,
                signals=signals,
                goal_text=str(draft.get("goal_text") or ""),
                injury_notes=str(draft.get("injury_notes") or ""),
            ),
            None,
            "deterministic_fallback",
        )

    knowledge = load_knowledge_bundle(
        knowledge_dir,
        query_text=_draft_blob(draft),
        draft=draft,
        mode="plan",
        total_budget=9000,
    )
    system = f"""Du er en norsk utholdenhetstrener som lager grovplan (meso-periodisering).
Bruk knowledge-basen. ÉN respons — ingen tool-kall.

Regler:
- Tilpass strukturen til utøveren (nybegynner ≠ comeback ≠ skade ≠ tidsklemma).
- Ikke hardkod Lofoten/William-volum med mindre utøveren ber om det.
- Beskytt mot for høyt volum; skade → ACWR-trygg progresjon.
- Returner KUN en fenced json-blokk:
```json
{{
  "athlete_archetype": "kort norsk label",
  "coach_note": "2-4 setninger på norsk",
  "weekly_hours_target": {weekly_hours},
  "season_start_date": "{season_start.isoformat()}",
  "goal_race_date": "{goal_race.isoformat()}",
  "plan_blocks": [
    {{"key":"…","title":"…","theme":"…","phase":"etablering|base|build|peak|taper|rehab|other",
      "start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD","weekly_hours":8.0,"sort_order":0}}
  ]
}}
```
- 3–8 blokker som dekker sesongvinduet uten store hull.
- Tema på norsk, konkrete (maks ~12 ord).

## Knowledge
{knowledge}
"""
    user = (
        "Lag periodiseringsplan ut fra denne utøverprofilen:\n"
        + json.dumps(
            {
                "draft": {
                    k: draft.get(k)
                    for k in (
                        "display_name",
                        "goal_text",
                        "injury_notes",
                        "schedule_notes",
                        "background_notes",
                        "coach_respect_notes",
                        "notes",
                        "weekly_hours_target",
                        "season_start_date",
                        "goal_race_date",
                        "ftp_tested",
                        "age_years",
                        "nutrition_ibs",
                        "nutrition_gluten",
                        "nutrition_lactose",
                    )
                },
                "signals": signals,
                "defaults": {
                    "season_start_date": season_start.isoformat(),
                    "goal_race_date": goal_race.isoformat(),
                    "weekly_hours_target": weekly_hours,
                },
            },
            ensure_ascii=False,
        )
    )
    try:
        reply = call_llm(
            api_key=api_key,
            model=model,
            system=system,
            history=[],
            user_message=user,
        )
    except Exception:
        return (
            _fallback_blocks(
                season_start=season_start,
                goal_race=goal_race,
                weekly_hours=weekly_hours,
                signals=signals,
                goal_text=str(draft.get("goal_text") or ""),
                injury_notes=str(draft.get("injury_notes") or ""),
            ),
            None,
            "deterministic_fallback",
        )

    data = _parse_json_object(reply)
    if not data:
        return (
            _fallback_blocks(
                season_start=season_start,
                goal_race=goal_race,
                weekly_hours=weekly_hours,
                signals=signals,
                goal_text=str(draft.get("goal_text") or ""),
                injury_notes=str(draft.get("injury_notes") or ""),
            ),
            None,
            "deterministic_fallback",
        )

    # Allow LLM to nudge hours/dates slightly
    wh = weekly_hours
    try:
        if data.get("weekly_hours_target") is not None:
            wh = float(data["weekly_hours_target"])
            wh = max(1.5, min(30.0, wh))
    except (TypeError, ValueError):
        pass
    ss = _parse_date(str(data.get("season_start_date") or "")) or season_start
    gr = _parse_date(str(data.get("goal_race_date") or "")) or goal_race
    blocks = normalize_plan_blocks(
        data.get("plan_blocks") if isinstance(data.get("plan_blocks"), list) else [],
        season_start=ss,
        goal_race=gr,
        weekly_hours=wh,
        signals=signals,
    )
    note = str(data.get("coach_note") or "").strip()[:900] or None
    arch = str(data.get("athlete_archetype") or "").strip()[:80]
    if arch:
        signals = {**signals, "_archetype": arch}  # type: ignore[dict-item]
    return blocks, note, "llm_knowledge"


def _draft_blob(draft: dict[str, Any]) -> str:
    parts = [
        str(draft.get(k) or "")
        for k in (
            "goal_text",
            "injury_notes",
            "schedule_notes",
            "background_notes",
            "coach_respect_notes",
            "notes",
        )
    ]
    return " ".join(parts)


def _combine_notes(draft: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, label in (
        ("notes", None),
        ("background_notes", "Bakgrunn"),
        ("coach_respect_notes", "Treneren skal respektere"),
    ):
        val = (draft.get(key) or "").strip()
        if not val:
            continue
        if label:
            parts.append(f"{label}: {val}")
        else:
            parts.append(val)
    return "\n\n".join(parts).strip()


def build_setup_preview(
    draft: dict[str, Any],
    *,
    knowledge_dir,
    api_key: str = "",
    model: str = "gpt-4o-mini",
    enrich: bool = True,
    today: date | None = None,
) -> dict[str, Any]:
    """Knowledge + athlete answers → periodization preview (no DB writes)."""
    signals = detect_athlete_signals(_draft_blob(draft), draft)
    start, race = default_season_window(
        season_start=draft.get("season_start_date"),
        goal_race=draft.get("goal_race_date"),
        today=today,
        signals=signals,
    )
    weekly = estimate_weekly_hours(
        draft.get("weekly_hours_target"),
        str(draft.get("schedule_notes") or ""),
        signals,
    )
    knowledge_meta = knowledge_selection_meta(
        knowledge_dir,
        query_text=_draft_blob(draft),
        draft=draft,
        mode="plan",
    )

    if enrich:
        blocks, coach_note, source = generate_plan_with_llm(
            draft,
            knowledge_dir=knowledge_dir,
            api_key=api_key,
            model=model,
            signals=signals,
            season_start=start,
            goal_race=race,
            weekly_hours=weekly,
        )
        # Re-read dates/hours if LLM shifted window via first/last block
        if blocks:
            start = _parse_date(blocks[0]["start_date"]) or start
            race = (_parse_date(blocks[-1]["end_date"]) or race) + timedelta(days=1)
    else:
        blocks = _fallback_blocks(
            season_start=start,
            goal_race=race,
            weekly_hours=weekly,
            signals=signals,
            goal_text=str(draft.get("goal_text") or ""),
            injury_notes=str(draft.get("injury_notes") or ""),
        )
        coach_note = None
        source = "deterministic_fallback"

    targets = season_targets_from_hours(weekly, start, race, signals)
    arch = str(signals.get("_archetype") or _archetype_label(signals))
    overview = build_overview_nb(
        blocks=blocks,
        season_start=start,
        goal_race=race,
        weekly_hours=weekly,
        targets=targets,
        goal_text=str(draft.get("goal_text") or ""),
        display_name=str(draft.get("display_name") or ""),
        signals=signals,
        athlete_archetype=arch,
        coach_note=coach_note,
    )

    athlete_patch = {
        "goal_text": (draft.get("goal_text") or "").strip(),
        "injury_notes": (draft.get("injury_notes") or "").strip(),
        "schedule_notes": (draft.get("schedule_notes") or "").strip(),
        "notes": _combine_notes(draft),
        "weekly_focus": (draft.get("weekly_focus") or "").strip()
        or (blocks[0]["theme"] if blocks else ""),
        "season_start_date": start.isoformat(),
        "goal_race_date": race.isoformat(),
        "season_swim_hours_target": targets["season_swim_hours_target"],
        "season_bike_hours_target": targets["season_bike_hours_target"],
        "season_run_hours_target": targets["season_run_hours_target"],
        "season_strength_hours_target": targets["season_strength_hours_target"],
        "ftp_tested": draft.get("ftp_tested"),
        "ftp_tested_at": draft.get("ftp_tested_at") or None,
        "weight_kg": draft.get("weight_kg"),
        "age_years": draft.get("age_years"),
        "nutrition_ibs": draft.get("nutrition_ibs") or "no",
        "nutrition_gluten": draft.get("nutrition_gluten") or "none",
        "nutrition_lactose": bool(draft.get("nutrition_lactose")),
        "nutrition_other_restrictions": draft.get("nutrition_other_restrictions")
        or "",
        "nutrition_notes": draft.get("nutrition_notes") or "",
        "agreements": draft.get("agreements")
        if isinstance(draft.get("agreements"), list)
        else [],
    }

    return {
        "overview_md": overview,
        "coach_note": coach_note,
        "llm_enriched": source == "llm_knowledge",
        "plan_source": source,
        "athlete_archetype": arch,
        "signals": {k: v for k, v in signals.items() if not str(k).startswith("_")},
        "knowledge": knowledge_meta,
        "weekly_hours_target": weekly,
        "season_start_date": start.isoformat(),
        "goal_race_date": race.isoformat(),
        "season_targets": targets,
        "plan_blocks": blocks,
        "athlete_patch": athlete_patch,
        "intervals_sync": {
            "will_push": False,
            "kind": "calendar_notes_and_workouts",
            "description": (
                "Etter bekreftelse av plan lokalt kan du velge å synce "
                "grovplan-noter (NOTE, ll-coach-…) pluss konkrete økter for "
                "første 1–2 uker (WORKOUT, ll-coach-w-…) til Intervals. "
                "Ingen ZWO — beskrivelse + varighet. Preview→confirm."
            ),
            "events_preview": [],
        },
        "persist_preview": {
            "sqlite": ["athletes", "plan_blocks", "athlete_secrets (valgfritt)"],
            "files": ["data/athletes/{id}/profile.md"],
            "intervals": "Kun etter ekstra Sync-bekreftelse (preview→confirm)",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def events_preview_for_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Backward-compatible note-only preview (prefer events_preview_for_plan_sync)."""
    from intervals_calendar import build_block_note_events, public_event_preview

    prepared = []
    for i, b in enumerate(blocks):
        prepared.append({**b, "id": b.get("id") or f"draft-{b.get('key') or i}"})
    events = build_block_note_events(prepared)
    return [public_event_preview(e) for e in events]


# --- Setup conversation (adaptive) ---

SETUP_EXTRACT_KEYS = (
    "goal_text",
    "injury_notes",
    "schedule_notes",
    "background_notes",
    "coach_respect_notes",
    "notes",
    "weekly_hours_target",
    "season_start_date",
    "goal_race_date",
    "ftp_tested",
    "weight_kg",
    "age_years",
    "nutrition_ibs",
    "nutrition_gluten",
    "nutrition_lactose",
    "nutrition_notes",
)


def build_setup_chat_system(
    draft: dict[str, Any],
    *,
    knowledge_dir,
    history_blob: str = "",
) -> tuple[str, dict[str, Any]]:
    knowledge = load_knowledge_bundle(
        knowledge_dir,
        query_text=_draft_blob(draft) + " " + history_blob,
        draft=draft,
        mode="chat",
        total_budget=6500,
    )
    meta = knowledge_selection_meta(
        knowledge_dir,
        query_text=_draft_blob(draft) + " " + history_blob,
        draft=draft,
        mode="chat",
    )
    coach = draft.get("coach_display_name") or "Rocky"
    name = draft.get("display_name") or "utøveren"
    system = f"""Du er {coach}, personlig utholdenhetstrener i onboarding-samtale med {name}.
Språk: norsk. Tone: konkret, nysgjerrig, ingen fluff. Én LLM-respons — ingen tools.

Mål for samtalen: forstå hvem utøveren er (nybegynner / comeback / skade / tidsklemma / annet),
mål, helse, bakgrunn, begrensninger, og fritekst du skal respektere.
Samle også Intervals-klarhet: foreslå å lime inn athlete ID + API-nøkkel når naturlig
(pek til Settings → Developer Settings) — tving det ikke før de er klare.

Regler:
- Still 1–2 spørsmål om gangen. Ikke et langt skjema.
- Ikke anta Lofoten/William/750t med mindre de sier det.
- Ikke diagnostiser skade/GI; tilpass og anbefal fagperson ved behov.
- Når du har nok til en grovplan (mål + omtrent tid/uke eller livssituasjon + helse-status),
  si at du kan lage forhåndsvisning, og sett ready_for_plan=true i extract.

Avslutt HVER melding med en fenced blokk merket setup_extract (ikke synlig råd):
```setup_extract
{{"ready_for_plan": false, "goal_text": null, "injury_notes": null, "schedule_notes": null,
 "background_notes": null, "coach_respect_notes": null, "weekly_hours_target": null,
 "season_start_date": null, "goal_race_date": null, "ftp_tested": null,
 "nutrition_ibs": null, "nutrition_gluten": null, "nutrition_lactose": null,
 "nutrition_notes": null, "notes": null}}
```
Kun fyll felt du faktisk har fått bekreftet; la resten være null.

## Kjent draft så langt
{json.dumps({k: draft.get(k) for k in SETUP_EXTRACT_KEYS if draft.get(k) not in (None, "", [])}, ensure_ascii=False)}

## Knowledge
{knowledge}
"""
    return system, meta


def extract_setup_fields(reply: str) -> tuple[str, dict[str, Any]]:
    """Strip setup_extract fence; merge non-null fields."""
    if not reply:
        return "", {}
    match = _EXTRACT_JSON_RE.search(reply)
    display = reply
    data: dict[str, Any] = {}
    if match:
        display = (_EXTRACT_JSON_RE.sub("", reply)).strip()
        raw = (match.group(1) or "").strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            data = {}
    cleaned: dict[str, Any] = {}
    for k, v in data.items():
        if v is None or v == "":
            continue
        if k == "ready_for_plan":
            cleaned[k] = bool(v)
            continue
        if k == "nutrition_lactose":
            cleaned[k] = bool(v)
            continue
        if k in ("weekly_hours_target", "ftp_tested", "weight_kg", "age_years"):
            try:
                cleaned[k] = float(v) if k != "age_years" else int(float(v))
            except (TypeError, ValueError):
                continue
            continue
        cleaned[k] = v
    return display.strip(), cleaned


def merge_draft(draft: dict[str, Any], extracted: dict[str, Any]) -> dict[str, Any]:
    out = dict(draft)
    for k, v in extracted.items():
        if k == "ready_for_plan":
            continue
        if v is None or v == "":
            continue
        out[k] = v
    return out
