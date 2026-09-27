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

from athlete_type import (
    infer_athlete_type,
    label_for,
    normalize_athlete_type,
    split_for,
)
from athlete_constraints import (
    constraints_summary_nb,
    normalize_disciplines,
    normalize_sessions_per_week,
    resolve_constraints,
    split_for_disciplines,
)
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


# Late-season default when athlete only gives a year (e.g. «triatlon 2028»).
_DEFAULT_GOAL_MONTH = 9
_DEFAULT_GOAL_DAY = 15


def infer_goal_race_date(
    *,
    goal_race: str | None = None,
    goal_text: str = "",
    schedule_notes: str = "",
    notes: str = "",
    today: date | None = None,
) -> date | None:
    """ISO date, or year-only («2028», «triatlon 2028») → mid/late that year.

    Never invents ~8 months ahead when the athlete named a future year.
    """
    today = today or date.today()
    explicit = _parse_date(goal_race)
    if explicit and explicit > today:
        return explicit

    blob = " ".join(
        str(x or "") for x in (goal_race, goal_text, schedule_notes, notes)
    )
    # Full ISO already handled; also «11. mai 2028» / «2028-08-20»
    m_iso = re.search(r"(20\d{2})-(\d{2})-(\d{2})", blob)
    if m_iso:
        try:
            d = date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
            if d > today:
                return d
        except ValueError:
            pass

    years = [int(y) for y in re.findall(r"\b(20[2-3]\d)\b", blob)]
    # Prefer the furthest future year mentioned (season target)
    future_years = sorted({y for y in years if y >= today.year}, reverse=True)
    if future_years:
        y = future_years[0]
        # Same calendar year mention without month → late this year if still ahead
        candidate = date(y, _DEFAULT_GOAL_MONTH, _DEFAULT_GOAL_DAY)
        if candidate <= today:
            # Year is current and default already passed → end of year
            candidate = date(y, 12, 15)
        if candidate <= today and y == today.year:
            return None  # fall through to week-based default
        if candidate > today:
            return candidate
    return None


def default_season_window(
    *,
    season_start: str | None = None,
    goal_race: str | None = None,
    today: date | None = None,
    signals: dict[str, bool] | None = None,
    goal_text: str = "",
    schedule_notes: str = "",
    notes: str = "",
) -> tuple[date, date]:
    today = today or date.today()
    start = _parse_date(season_start) or _monday_on_or_after(today)
    signals = signals or {}
    race = infer_goal_race_date(
        goal_race=goal_race,
        goal_text=goal_text,
        schedule_notes=schedule_notes,
        notes=notes,
        today=today,
    )
    if not race or race <= start:
        # Only when no conversational year/date — beginners shorter, rebuild longer
        weeks = 24 if signals.get("beginner") else 40 if signals.get("returning") else 32
        if signals.get("time_constrained"):
            weeks = min(weeks, 28)
        if signals.get("fitness_ok") and not signals.get("returning"):
            weeks = max(weeks, 36)  # trained → longer season, not rebuild sprint
        race = start + timedelta(weeks=weeks)
    return start, race


def _draft_text_blob(draft: dict[str, Any] | None, *extra: str) -> str:
    draft = draft or {}
    parts = list(extra)
    for k in (
        "goal_text",
        "schedule_notes",
        "background_notes",
        "coach_respect_notes",
        "notes",
        "injury_notes",
        "fitness_notes",
        "weekly_focus",
    ):
        parts.append(str(draft.get(k) or ""))
    agr = draft.get("agreements")
    if isinstance(agr, list):
        parts.extend(str(a) for a in agr)
    return " ".join(parts)


def compose_goal_text(draft: dict[str, Any] | None = None, *, text: str = "") -> str:
    """Build a non-empty Du-fanen «Mål» string from extract / conversation cues."""
    draft = draft or {}
    explicit = str(draft.get("goal_text") or "").strip()
    if explicit:
        return explicit[:500]

    blob = _draft_text_blob(draft, text)
    low = blob.lower()
    bits: list[str] = []

    if re.search(r"triatlon|triathlon|half\s*extreme|halviron|ironman|norseman", low):
        bits.append("Triatlon")
    elif re.search(r"halv\s*maraton|half[\s-]?marathon", low):
        bits.append("Halvmaraton")
    elif re.search(r"\bmaraton\b|marathon", low):
        bits.append("Maraton")
    elif re.search(r"\bløp|\bløper|running", low):
        bits.append("Løping")
    elif re.search(r"sykkel|cycling", low):
        bits.append("Sykling")

    years = re.findall(r"\b(20[2-3]\d)\b", blob)
    if years:
        bits.append(max(years))  # furthest / latest mentioned year as season target

    if re.search(r"lofoten", low):
        bits.append("Lofoten")

    if re.search(r"fullføre|fullfor", low):
        bits.append("fullføre")
    elif re.search(r"prestasjon|podium|sub[\s-]?\d", low):
        bits.append("prestasjon")

    if bits:
        # «Triatlon 2028» or «Halvmaraton · fullføre»
        if len(bits) >= 2 and bits[1].isdigit():
            return f"{bits[0]} {bits[1]}"[:500]
        return " · ".join(bits)[:500]

    # Last resort: first non-empty note line that looks like a goal
    for key in ("background_notes", "schedule_notes", "notes", "coach_respect_notes"):
        val = str(draft.get(key) or "").strip()
        if val and len(val) >= 8:
            return val.split("\n")[0][:500]
    return ""


def compose_fitness_notes(draft: dict[str, Any] | None = None, *, text: str = "") -> str:
    draft = draft or {}
    explicit = str(draft.get("fitness_notes") or "").strip()
    if explicit:
        return explicit[:400]
    blob = _draft_text_blob(draft, text).lower()
    if re.search(
        r"form\s+(er\s+)?(ok|grei|bra|fin|god)|allerede\s+i\s+form|trener\s+allerede|"
        r"fitness\s+ok|ikke\s+comeback|ikke\s+nybegynner|holder\s+formen",
        blob,
    ):
        return "Form OK — trener allerede (ikke re-etablering)"
    return ""


def build_agreements_list(
    draft: dict[str, Any] | None = None,
    *,
    constraints: dict[str, Any] | None = None,
    goal_text: str = "",
    fitness_notes: str = "",
) -> list[str]:
    """Human-readable agreements for Du-fanen + profile.md."""
    draft = draft or {}
    existing = draft.get("agreements")
    out: list[str] = []
    if isinstance(existing, list):
        out.extend(str(a).strip() for a in existing if str(a).strip())

    def _add(line: str) -> None:
        line = line.strip()
        if line and line not in out:
            out.append(line)

    if goal_text:
        _add(f"Mål: {goal_text}")
    if fitness_notes:
        _add(fitness_notes)
    c = constraints or {}
    n = c.get("sessions_per_week")
    if n:
        _add(f"{n} økter/uke")
    labels = c.get("disciplines_labels_no") or []
    if labels:
        _add("Disipliner: " + " + ".join(labels))
    at = draft.get("athlete_type") or c.get("athlete_type")
    if at:
        _add(f"Utøvertype: {at}")
    race = draft.get("goal_race_date")
    if race:
        _add(f"Måldato: {race}")
    return out[:20]


def enrich_draft_from_text(
    draft: dict[str, Any],
    text: str = "",
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Heuristic fill for chat/preview when LLM extract leaves fields null."""
    out = dict(draft)
    blob = _draft_text_blob(draft, text)
    low = blob.lower()

    if not str(out.get("goal_text") or "").strip():
        composed = compose_goal_text(out, text=text)
        if composed:
            out["goal_text"] = composed

    if not str(out.get("fitness_notes") or "").strip():
        fit = compose_fitness_notes(out, text=text)
        if fit:
            out["fitness_notes"] = fit

    if not out.get("goal_race_date"):
        inferred = infer_goal_race_date(
            goal_race=out.get("goal_race_date"),
            goal_text=str(out.get("goal_text") or ""),
            schedule_notes=str(out.get("schedule_notes") or ""),
            notes=blob,
            today=today,
        )
        if inferred:
            out["goal_race_date"] = inferred.isoformat()

    # Sessions / schedule crumbs into schedule_notes if empty
    if not str(out.get("schedule_notes") or "").strip():
        m = re.search(
            r"(\d)\s*(?:økter|okter|sessions?|ganger)\s*(?:/|per|i)?\s*uke",
            low,
        )
        if m:
            out["schedule_notes"] = f"{m.group(1)} økter/uke"
            out.setdefault("sessions_per_week", int(m.group(1)))
        elif re.search(r"\d+\s*t", low):
            out["schedule_notes"] = text.strip()[:400] if text.strip() else blob[:400]

    return out


def merge_confirm_athlete_patch(
    patch: dict[str, Any],
    body: dict[str, Any],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Prefer non-empty patch, then body; synthesize goal/agreements for Du-fanen."""
    persist_keys = (
        "goal_text",
        "weekly_focus",
        "fitness_notes",
        "schedule_notes",
        "injury_notes",
        "background_notes",
        "coach_respect_notes",
        "notes",
        "goal_race_date",
        "season_start_date",
        "athlete_type",
        "sport",
        "sessions_per_week",
        "allowed_disciplines",
        "season_swim_hours_target",
        "season_bike_hours_target",
        "season_run_hours_target",
        "season_strength_hours_target",
        "ftp_tested",
        "ftp_tested_at",
        "weight_kg",
        "age_years",
        "nutrition_ibs",
        "nutrition_gluten",
        "nutrition_lactose",
        "nutrition_other_restrictions",
        "nutrition_notes",
        "agreements",
    )
    merged_draft: dict[str, Any] = {}
    for k in persist_keys:
        pv = (patch or {}).get(k)
        bv = body.get(k)
        if pv not in (None, "", []):
            merged_draft[k] = pv
        elif bv not in (None, "", []):
            merged_draft[k] = bv
    # Keep display fields for compose helpers
    for k in ("display_name", "username", "coach_display_name"):
        if body.get(k):
            merged_draft[k] = body[k]

    merged_draft = enrich_draft_from_text(merged_draft, today=today)
    goal = compose_goal_text(merged_draft)
    fitness = compose_fitness_notes(merged_draft)
    atype = merged_draft.get("athlete_type")
    constraints = resolve_constraints(draft=merged_draft, athlete_type=atype)
    if merged_draft.get("sessions_per_week") in (None, ""):
        merged_draft["sessions_per_week"] = constraints.get("sessions_per_week")
    if not merged_draft.get("allowed_disciplines"):
        merged_draft["allowed_disciplines"] = constraints.get("allowed_disciplines") or []

    out = {k: (patch or {}).get(k) for k in (patch or {}) if k in persist_keys}
    out.update({k: merged_draft[k] for k in persist_keys if k in merged_draft})
    out["goal_text"] = goal
    out["fitness_notes"] = fitness
    if not str(out.get("injury_notes") or "").strip():
        out["injury_notes"] = str(merged_draft.get("injury_notes") or "").strip()
    if not str(out.get("weekly_focus") or "").strip():
        n = merged_draft.get("sessions_per_week")
        labels = constraints.get("disciplines_labels_no") or []
        disc = " + ".join(labels) if labels else "utholdenhet"
        out["weekly_focus"] = (
            f"{n} økter/uke · {disc}" if n else f"Kontinuitet · {disc}"
        )[:160]
    out["sessions_per_week"] = merged_draft.get("sessions_per_week")
    out["allowed_disciplines"] = merged_draft.get("allowed_disciplines") or []
    out["athlete_type"] = merged_draft.get("athlete_type") or out.get("athlete_type")
    if merged_draft.get("goal_race_date"):
        out["goal_race_date"] = merged_draft["goal_race_date"]
    if merged_draft.get("season_start_date"):
        out["season_start_date"] = merged_draft["season_start_date"]
    out["agreements"] = build_agreements_list(
        merged_draft,
        constraints=constraints,
        goal_text=goal,
        fitness_notes=fitness,
    )
    notes = _combine_notes(merged_draft)
    if fitness and fitness not in notes:
        notes = (notes + "\n\n" + fitness).strip() if notes else fitness
    out["notes"] = notes
    out["schedule_notes"] = str(merged_draft.get("schedule_notes") or "").strip()
    return out


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


def season_targets_from_hours(
    weekly_hours: float,
    start: date,
    race: date,
    signals: dict[str, bool] | None = None,
    *,
    athlete_type: str | None = None,
    allowed_disciplines: list[str] | None = None,
) -> dict[str, float]:
    signals = signals or {}
    if athlete_type:
        split = split_for(athlete_type)
    elif signals.get("beginner") and not signals.get("multisport"):
        split = {"swim": 0.05, "bike": 0.25, "run": 0.55, "strength": 0.15}
    else:
        split = split_for(None)
    if allowed_disciplines:
        split = split_for_disciplines(athlete_type, allowed_disciplines, base_split=split)
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
    athlete_type: str | None = None,
    allowed_disciplines: list[str] | None = None,
    sessions_per_week: int | None = None,
) -> list[dict[str, Any]]:
    """Adaptive fallback when LLM unavailable — still signal-aware, not one template."""
    if goal_race <= season_start:
        goal_race = season_start + timedelta(weeks=16)
    total_days = max(28, (goal_race - season_start).days)
    end_plan = goal_race - timedelta(days=1)
    run_primary = (athlete_type or "").endswith("runner") or athlete_type == "runner"
    fitness_ok = bool(signals.get("fitness_ok"))
    discs = set(allowed_disciplines or [])
    # Trained athlete already training N×/week → base/build, never «Re-etablering»
    use_rebuild = bool(signals.get("returning")) and not fitness_ok

    if signals.get("beginner"):
        templates = [
            ("grunnlag", "Grunnlag", "etablering", "Vaner · teknikk · lav intensitet", 0.25, 0.75),
            ("base", "Base", "base", "Aerob kontinuitet", 0.35, 0.95),
            ("utvikling", "Utvikling", "build", "Lett kvalitet når stabil", 0.25, 1.05),
            ("målblokk", "Mot mål", "peak", "Spesifikk rolig oppbygging", 0.10, 1.0),
            ("taper", "Nedtrapping", "taper", "Frisk til start / milesten", 0.05, 0.70),
        ]
    elif run_primary and "half_marathon" in (athlete_type or ""):
        templates = [
            ("grunnlag", "Grunnlag", "etablering", "Løpsvaner · skadefri base", 0.20, 0.80),
            ("base", "Base", "base", "Aerob km · langtur vokser", 0.30, 0.95),
            ("utvikling", "Utvikling", "build", "Terskel / bakke · HM-spesifikt", 0.30, 1.05),
            ("målblokk", "Mot HM", "peak", "Race-pace · langtur topp", 0.15, 1.0),
            ("taper", "Nedtrapping", "taper", "Frisk til halvmaraton", 0.05, 0.65),
        ]
    elif run_primary:
        templates = [
            ("grunnlag", "Grunnlag", "etablering", "Løpskontinuitet · styrke", 0.20, 0.80),
            ("base", "Base", "base", "Aerob volum", 0.35, 0.95),
            ("utvikling", "Utvikling", "build", "Kvalitet · langtur", 0.30, 1.05),
            ("målblokk", "Mot mål", "peak", "Spesifikk løpsform", 0.10, 1.0),
            ("taper", "Nedtrapping", "taper", "Frisk til start", 0.05, 0.70),
        ]
    elif signals.get("injury"):
        templates = [
            ("rehab", "Rehab / skånsom", "etablering", "Belastningsstyring · ACWR-trygg", 0.20, 0.60),
            ("rebuild", "Rebuild", "base", "Gradvis volum · styrke", 0.30, 0.85),
            ("base", "Base", "base", "Aerob base uten forcering", 0.25, 1.0),
            ("build", "Build", "build", "Kvalitet når smertefri", 0.15, 1.05),
            ("taper", "Buffer / taper", "taper", "Margin før mål", 0.10, 0.75),
        ]
    elif use_rebuild:
        templates = [
            ("kontakt", "Re-etablering", "etablering", "Kontakt alle ben · ikke 2019-watt", 0.15, 0.70),
            ("base1", "Base 1", "base", "Aerob · teknikk", 0.25, 0.90),
            ("base2", "Base 2", "base", "Volum opp kontrollert", 0.25, 1.05),
            ("build", "Build", "build", "Kvalitet / spesifikk", 0.20, 1.15),
            ("peak", "Peak", "peak", "Race-spesifikk", 0.10, 1.05),
            ("taper", "Taper", "taper", "Nedtrapping", 0.05, 0.65),
        ]
    elif fitness_ok or (sessions_per_week and sessions_per_week <= 5):
        sess_bit = f"{sessions_per_week} økter/uke · " if sessions_per_week else ""
        templates = [
            ("base1", "Base", "base", f"{sess_bit}Aerob kontinuitet", 0.30, 0.95),
            ("base2", "Base 2", "base", "Volum og teknikk", 0.25, 1.0),
            ("build", "Build", "build", "Kvalitet / spesifikk", 0.25, 1.10),
            ("peak", "Peak", "peak", "Race-spesifikk", 0.12, 1.05),
            ("taper", "Taper", "taper", "Nedtrapping", 0.08, 0.70),
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

    # Discipline-aware theme tweaks (no swim/bike language when not allowed)
    def _theme_for(theme: str) -> str:
        t = theme
        if discs and "swim" not in discs and "bike" not in discs:
            t = re.sub(r"\b(svøm|sykkel|swim|bike|alle ben)\b", "", t, flags=re.I)
            t = re.sub(r"\s{2,}", " ", t).strip(" ·")
            if not t:
                t = "Løp + styrke · kontinuitet" if "run" in discs else "Kontinuitet"
        return t

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
        theme_n = _theme_for(theme)
        t = theme_n + injury_bit
        if goal_text and phase in ("build", "peak"):
            t = f"{theme_n} · mot {(goal_text.strip().split(chr(10))[0])[:60]}{injury_bit}"
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


def _sanitize_block_titles(
    blocks: list[dict[str, Any]],
    *,
    signals: dict[str, bool],
    allowed_disciplines: list[str] | None = None,
    fitness_notes: str = "",
) -> list[dict[str, Any]]:
    """Strip false re-etablering / wrong-discipline themes after LLM or fallback."""
    fitness_ok = bool(signals.get("fitness_ok")) or bool(
        re.search(r"form ok|ikke re-etablering|trener allerede", (fitness_notes or "").lower())
    )
    discs = set(allowed_disciplines or [])
    out: list[dict[str, Any]] = []
    for b in blocks:
        nb = dict(b)
        title = str(nb.get("title") or "")
        theme = str(nb.get("theme") or "")
        if fitness_ok and re.search(r"re-?etablering|rebuild", title, re.I):
            nb["title"] = "Base"
            if nb.get("phase") in ("etablering", "rehab"):
                nb["phase"] = "base"
            theme = re.sub(r"re-?etablering", "base", theme, flags=re.I)
        if discs and "swim" not in discs and "bike" not in discs:
            theme = re.sub(
                r"(langsykler?|lang\s*sykkel|svømmeteknikk|svøm|sykkel|swim|bike)",
                "",
                theme,
                flags=re.I,
            )
            theme = re.sub(r"\s{2,}", " ", theme).strip(" ·,/")
            if not theme:
                theme = "Løp + styrke" if "run" in discs else "Kontinuitet"
            title = re.sub(
                r"(langsykler?|svømmeteknikk|svøm|sykkel)",
                "",
                title,
                flags=re.I,
            ).strip(" ·") or nb["title"]
            nb["title"] = title
        nb["theme"] = theme
        out.append(nb)
    return out


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


def _archetype_label(
    signals: dict[str, bool],
    *,
    athlete_type: str | None = None,
) -> str:
    if athlete_type:
        return label_for(athlete_type)
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
    athlete_type: str | None = None,
) -> tuple[list[dict[str, Any]], str | None, str]:
    """One LLM pass → blocks + coach_note. Returns (blocks, note, source)."""
    fb_kwargs = dict(
        season_start=season_start,
        goal_race=goal_race,
        weekly_hours=weekly_hours,
        signals=signals,
        goal_text=str(draft.get("goal_text") or ""),
        injury_notes=str(draft.get("injury_notes") or ""),
        athlete_type=athlete_type,
    )
    if not api_key:
        return (_fallback_blocks(**fb_kwargs), None, "deterministic_fallback")

    knowledge = load_knowledge_bundle(
        knowledge_dir,
        query_text=_draft_blob(draft),
        draft=draft,
        mode="plan",
        total_budget=9000,
    )
    type_label = label_for(athlete_type) if athlete_type else "ukjent"
    discipline_hint = ""
    discs = draft.get("allowed_disciplines") or []
    sess = draft.get("sessions_per_week")
    fitness = str(draft.get("fitness_notes") or "")
    if athlete_type and (
        str(athlete_type).endswith("runner") or athlete_type == "runner"
    ):
        discipline_hint = (
            "Hoveddisiplin er LØPING — ikke bygg triatlon-periodisering med "
            "svøm/sykkel som primærvolum. Styrke + ev. lett cross-training OK."
        )
    elif athlete_type == "cyclist":
        discipline_hint = "Hoveddisiplin er SYKKEL — ikke default tri-pack."
    elif athlete_type == "swimmer":
        discipline_hint = "Hoveddisiplin er SVØMMING — ikke default tri-pack."
    if discs:
        discipline_hint += (
            f" Tillatte disipliner: {discs}. Temaer må matche — "
            "ikke «langsykkel/svøm» hvis det ikke er avtalt."
        )
    if sess:
        discipline_hint += f" Avtalt frekvens: ca. {sess} økter/uke."
    if signals.get("fitness_ok") or re.search(r"form ok|trener allerede", fitness, re.I):
        discipline_hint += (
            " Form er allerede OK / trener allerede — bruk Base/Build, "
            "IKKE tittel «Re-etablering»."
        )

    system = f"""Du er en norsk utholdenhetstrener som lager grovplan (meso-periodisering).
Bruk knowledge-basen. ÉN respons — ingen tool-kall.

Utøvertype (hoveddisiplin): {type_label} ({athlete_type or "general_endurance"}).
{discipline_hint}

Regler:
- Tilpass strukturen til utøveren (nybegynner ≠ comeback ≠ skade ≠ tidsklemma ≠ enkeltidrett).
- Respekter hoveddisiplin og allowed_disciplines — halvmaraton-løper skal IKKE få swim/bike/run-tri-mal.
- goal_race_date i defaults er fasit for sesongslutt — ikke flytt til ~8 mnd hvis året er 2028+.
- Form OK / trener allerede N×/uke → første blokk «Base» (ikke Re-etablering).
- Ikke hardkod Lofoten/William-volum med mindre utøveren ber om det.
- Beskytt mot for høyt volum; skade → ACWR-trygg progresjon.
- Returner KUN en fenced json-blokk:
```json
{{
  "athlete_archetype": "kort norsk label (inkl. hoveddisiplin)",
  "athlete_type": "{athlete_type or "general_endurance"}",
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
                        "fitness_notes",
                        "weekly_hours_target",
                        "sessions_per_week",
                        "allowed_disciplines",
                        "season_start_date",
                        "goal_race_date",
                        "ftp_tested",
                        "age_years",
                        "nutrition_ibs",
                        "nutrition_gluten",
                        "nutrition_lactose",
                        "athlete_type",
                        "sport",
                    )
                },
                "signals": {k: v for k, v in signals.items() if not str(k).startswith("_")},
                "athlete_type": athlete_type,
                "athlete_type_label": type_label,
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
        return (_fallback_blocks(**fb_kwargs), None, "deterministic_fallback")

    data = _parse_json_object(reply)
    if not data:
        return (_fallback_blocks(**fb_kwargs), None, "deterministic_fallback")

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
            "athlete_type",
            "sport",
            "weekly_focus",
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
    today = today or date.today()
    draft = enrich_draft_from_text(dict(draft), today=today)
    goal_text = compose_goal_text(draft)
    fitness_notes = compose_fitness_notes(draft)
    if goal_text:
        draft["goal_text"] = goal_text
    if fitness_notes:
        draft["fitness_notes"] = fitness_notes

    signals = detect_athlete_signals(_draft_blob(draft), draft)
    type_info = infer_athlete_type(_draft_blob(draft), draft, signals=signals)
    athlete_type = type_info["athlete_type"]
    draft_for_constraints = {**draft, "athlete_type": athlete_type}
    constraints = resolve_constraints(
        draft=draft_for_constraints, athlete_type=athlete_type
    )
    allowed_disciplines = constraints["allowed_disciplines"]
    sessions_per_week = constraints["sessions_per_week"]
    start, race = default_season_window(
        season_start=draft.get("season_start_date"),
        goal_race=draft.get("goal_race_date"),
        today=today,
        signals=signals,
        goal_text=goal_text or str(draft.get("goal_text") or ""),
        schedule_notes=str(draft.get("schedule_notes") or ""),
        notes=_draft_text_blob(draft),
    )
    draft["goal_race_date"] = race.isoformat()
    draft["season_start_date"] = start.isoformat()
    weekly = estimate_weekly_hours(
        draft.get("weekly_hours_target"),
        str(draft.get("schedule_notes") or ""),
        signals,
    )
    knowledge_meta = knowledge_selection_meta(
        knowledge_dir,
        query_text=_draft_blob(draft),
        draft={
            **draft,
            "athlete_type": athlete_type,
            "allowed_disciplines": allowed_disciplines,
            "sessions_per_week": sessions_per_week,
        },
        mode="plan",
    )

    if enrich:
        blocks, coach_note, source = generate_plan_with_llm(
            {
                **draft,
                "allowed_disciplines": allowed_disciplines,
                "sessions_per_week": sessions_per_week,
                "fitness_notes": fitness_notes,
            },
            knowledge_dir=knowledge_dir,
            api_key=api_key,
            model=model,
            signals=signals,
            season_start=start,
            goal_race=race,
            weekly_hours=weekly,
            athlete_type=athlete_type,
        )
        if blocks:
            start = _parse_date(blocks[0]["start_date"]) or start
            race = (_parse_date(blocks[-1]["end_date"]) or race) + timedelta(days=1)
            # Never let LLM shrink a named future year (e.g. 2028) back to ~8 months
            named = infer_goal_race_date(
                goal_text=goal_text,
                schedule_notes=str(draft.get("schedule_notes") or ""),
                notes=_draft_text_blob(draft),
                today=today,
            )
            if named and race.year < named.year:
                race = named
    else:
        blocks = _fallback_blocks(
            season_start=start,
            goal_race=race,
            weekly_hours=weekly,
            signals=signals,
            goal_text=goal_text,
            injury_notes=str(draft.get("injury_notes") or ""),
            athlete_type=athlete_type,
            allowed_disciplines=allowed_disciplines,
            sessions_per_week=sessions_per_week,
        )
        coach_note = None
        source = "deterministic_fallback"

    # Rewrite false re-etablering when form OK / trained frequency
    blocks = _sanitize_block_titles(
        blocks,
        signals=signals,
        allowed_disciplines=allowed_disciplines,
        fitness_notes=fitness_notes,
    )

    targets = season_targets_from_hours(
        weekly,
        start,
        race,
        signals,
        athlete_type=athlete_type,
        allowed_disciplines=allowed_disciplines,
    )
    arch = _archetype_label(signals, athlete_type=athlete_type)
    overview = build_overview_nb(
        blocks=blocks,
        season_start=start,
        goal_race=race,
        weekly_hours=weekly,
        targets=targets,
        goal_text=goal_text,
        display_name=str(draft.get("display_name") or ""),
        signals=signals,
        athlete_archetype=arch,
        coach_note=coach_note,
    )

    labels = constraints.get("disciplines_labels_no") or []
    disc = " + ".join(labels) if labels else "utholdenhet"
    weekly_focus = (draft.get("weekly_focus") or "").strip()
    if not weekly_focus:
        if sessions_per_week:
            weekly_focus = f"{sessions_per_week} økter/uke · {disc}"
        elif blocks:
            weekly_focus = str(blocks[0].get("theme") or "")[:160]
        else:
            weekly_focus = f"Kontinuitet · {disc}"

    agreements = build_agreements_list(
        {**draft, "athlete_type": athlete_type, "goal_race_date": race.isoformat()},
        constraints=constraints,
        goal_text=goal_text,
        fitness_notes=fitness_notes,
    )
    notes = _combine_notes(draft)
    if fitness_notes and fitness_notes not in notes:
        notes = (notes + "\n\n" + fitness_notes).strip() if notes else fitness_notes

    athlete_patch = {
        "goal_text": goal_text,
        "injury_notes": (draft.get("injury_notes") or "").strip(),
        "schedule_notes": (draft.get("schedule_notes") or "").strip(),
        "notes": notes,
        "fitness_notes": fitness_notes,
        "weekly_focus": weekly_focus[:160],
        "athlete_type": athlete_type,
        "sport": type_info.get("sport") or draft.get("sport") or "endurance",
        "allowed_disciplines": allowed_disciplines,
        "sessions_per_week": sessions_per_week,
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
        "agreements": agreements,
    }

    return {
        "overview_md": overview,
        "coach_note": coach_note,
        "llm_enriched": source == "llm_knowledge",
        "plan_source": source,
        "athlete_archetype": arch,
        "athlete_type": athlete_type,
        "athlete_type_label": type_info["label_no"],
        "athlete_type_meta": {
            "source": type_info["source"],
            "sport": type_info["sport"],
            "split": type_info["split"],
        },
        "constraints": constraints,
        "constraints_summary_nb": constraints_summary_nb(constraints),
        "signals": {k: v for k, v in signals.items() if not str(k).startswith("_")},
        "knowledge": knowledge_meta,
        "weekly_hours_target": weekly,
        "sessions_per_week": sessions_per_week,
        "allowed_disciplines": allowed_disciplines,
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
                f"Avtale: {constraints_summary_nb(constraints)}. Preview→confirm."
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
    "fitness_notes",
    "weekly_hours_target",
    "sessions_per_week",
    "allowed_disciplines",
    "season_start_date",
    "goal_race_date",
    "ftp_tested",
    "weight_kg",
    "age_years",
    "nutrition_ibs",
    "nutrition_gluten",
    "nutrition_lactose",
    "nutrition_notes",
    "athlete_type",
    "sport",
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
Språk: norsk. Tone: konkret, trygg, ærlig — ingen fluff, ingen tippy tips-liste. Én LLM-respons — ingen tools.
Du er hovedtrener, ikke kundeservice: én klar anbefaling når du gir råd; pushback hvis volum/mål er urealistisk.

Mål for samtalen: forstå hvem utøveren er (nybegynner / comeback / skade / tidsklemma),
hoveddisiplin / utøvertype (f.eks. halvmaraton-løper, syklist, triatlet, nybegynner flersport),
mål, helse, bakgrunn, begrensninger, og fritekst du skal respektere.
Samle også Intervals-klarhet: foreslå å lime inn athlete ID + API-nøkkel når naturlig
(pek til Settings → Developer Settings) — tving det ikke før de er klare.

Regler:
- Still 1–2 spørsmål om gangen. Ikke et langt skjema.
- Ikke anta Lofoten/William/750t med mindre de sier det.
- Ikke diagnostiser skade/GI; tilpass og anbefal fagperson ved behov.
- Når du har nok til en grovplan (mål + omtrent tid/uke eller livssituasjon + helse-status),
  si at du kan lage forhåndsvisning, og sett ready_for_plan=true i extract.
- Sett athlete_type når du er sikker, f.eks.:
  half_marathon_runner | marathon_runner | runner | cyclist | swimmer |
  triathlete | beginner_multi | general_endurance
- Sett sessions_per_week (heltall 2–8) når utøveren sier f.eks. «3 økter i uka».
- Sett allowed_disciplines som liste når avtalt, f.eks. ["run","strength"]
  (gyldige: run, bike, swim, strength). Halvmaraton/løper uten tri → ikke svøm/sykkel.
- Når utøveren nevner år («triatlon 2028»), sett goal_race_date til sen sesong det året
  (f.eks. YYYY-09-15) ELLER spør én gang om eksakt racedato — aldri finn opp ~8 mnd frem.
- Når form er OK / trener allerede: sett fitness_notes (kort) — ikke merk som comeback.

Avslutt HVER melding med en fenced blokk merket setup_extract (ikke synlig råd):
```setup_extract
{{"ready_for_plan": false, "goal_text": null, "injury_notes": null, "schedule_notes": null,
 "background_notes": null, "coach_respect_notes": null, "weekly_hours_target": null,
 "sessions_per_week": null, "allowed_disciplines": null, "fitness_notes": null,
 "season_start_date": null, "goal_race_date": null, "ftp_tested": null,
 "nutrition_ibs": null, "nutrition_gluten": null, "nutrition_lactose": null,
 "nutrition_notes": null, "notes": null, "athlete_type": null, "sport": null}}
```
Kun fyll felt du faktisk har fått bekreftet; la resten være null.
Alltid fyll goal_text så snart målet er klart (f.eks. «Triatlon 2028») — Du-fanen trenger det.

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
        if k == "athlete_type":
            norm = normalize_athlete_type(v)
            if norm:
                cleaned[k] = norm
            continue
        if k == "sessions_per_week":
            n = normalize_sessions_per_week(v)
            if n is not None:
                cleaned[k] = n
            continue
        if k == "allowed_disciplines":
            discs = normalize_disciplines(v)
            if discs:
                cleaned[k] = discs
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
