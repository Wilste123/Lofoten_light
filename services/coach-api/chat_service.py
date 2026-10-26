"""Single-LLM-call chat — no intent router, no tool loop.

Main Coach-tab chat (`POST /v1/chat`), session-detail chat (same endpoint +
`session_id`), and setup chat share the same honest coach voice via
``HONEST_COACH_VOICE`` (imported by setup_plan).
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from pathlib import Path

from knowledge_ctx import knowledge_selection_meta, load_knowledge_bundle, session_query_text
from profile import load_profile_md


PERSONALITY_HINTS = {
    "direkte": (
        "Direkte, trygg og konkret — erfaren utholdenhetstrener. "
        "Én anbefaling, ikke tips-liste. Si nei når forespørselen er urealistisk eller skaderisikabel."
    ),
    "støttende": (
        "Støttende men ærlig; ros steady progress. "
        "Utfordre urealistisk volum — ikke bli myk eller tippy."
    ),
    "teknisk": (
        "Teknisk og presis; soner, TSS, struktur. "
        "Konkrete tall, ikke generiske råd. Avvis dårlige intensitetsvalg."
    ),
    "opv": (
        "Ole Petter Vibekken-inspirert: struktur, krav, ærlig risiko — tilpasset tri/comeback. "
        "Korte setninger, konkrete tall, pushback når det smaker 2019-volum."
    ),
}

# One coherent voice for ALL chat surfaces (Coach-fane, session-fokus, setup).
# Aligned with AGENTS.md + knowledge/coach/* (OPV / agent-modus), not a card-machine.
HONEST_COACH_VOICE = """
Du er hovedtrener — ikke kundeservice, ikke motivasjonsplakat, ikke et kort-API (ikke tippy).
Stemme (OPV / agent-modus) — selvsikker og anbefalingsorientert:
- Norsk, jordnær, korte setninger. Konkrete tall (min, %, RPE, watt når relevant). Én klar anbefaling.
- Fakta (snapshot/profil/knowledge) → observasjon → anbefaling. Skill planlagt fra gjennomført.
- Utfordre 2019-volum-tankning. Historisk FTP 410 W er IKKE dagens intensitet.
- Når mål + erfaring/form/økter-uke ikke henger: si «dette er ikke realistisk slik det står nå»,
  begrunn kort, gi 2–4 konkrete alternativer (fra knowledge: maalrealisme, feil-og-fixes, load).
- Ros kontinuitet og smarte valg — ikke hero-TSS. Plan B når tid/vær/energi er usikkert.
- Be om 1–2 nøkkelspørsmål når du mangler info — ikke intervju.
- Når utøveren godtar et alternativ: bekreft avtalen eksplisitt i prosa; bruk agreements_update-fence
  KUN når de eksplisitt godtar/endrer avtale (så Human Coach-kortet kan lagre).
- Samtale først: de fleste turer er sparring/analyse/råd UTEN kort. Ikke spam forhåndsvisning.
- Ingen Pondus/tool-loop. Én LLM-respons. Ingen tom motivasjon.
- Wellness (søvn/HRV/RHR/CTL): signaler, ikke fasit — vei inn, ikke omskriv hele planen etter ett tall.
- Ingen medisinsk diagnose. Ved smerte/GI: tilpass råd, anbefal fagperson ved behov.
""".strip()

# Compact write protocol — only when athlete explicitly asks to change plan/calendar.
_WRITE_PROTOCOL_NB = """
Skrivemodus (KUN når utøveren eksplisitt ber om å legge inn / endre / synke / bygge om plan eller økt):
- App planned_sessions = planlagt; Intervals-aktiviteter = gjennomført. Du synker IKKE selv.
- ALDRI si at noe er lagret/synket før utøveren bekrefter Human Coach-kortet.
- Én fenced block når det trengs (ellers ingen fence):
  • workout_proposal → {{"workouts":[{{"name","date","sport","duration_minutes","description","start_time"}}]}}
  • workout_removal → {{"external_ids","dates","names"}} (kun ll-coach-*)
  • agreements_update → kun avtalte felt (sessions_per_week, goal_*, allowed_disciplines, agreements, reason)
  • athlete_type_update → {{"athlete_type","reason"}}
  • plan_update → {{"reason","rebuild","ease_load","scope":"week"|"full","week_start"?}}
- Sync-forespørsel: prosa + app emitter Sync-kort — ALDRI workout_proposal/plan_update for sync.
- Vanlig råd / «hva synes du» / analyse / sliten / spørsmål: BARE prosa — ingen fence, ingen kort.
""".strip()

# Optional structured proposal the UI can preview→confirm onto Intervals.
_WORKOUT_PROPOSAL_RE = re.compile(
    r"```(?:json\s+)?workout_proposal\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
# LLM sometimes forgets the workout_proposal label and dumps ```json {workouts…}
_GENERIC_WORKOUTS_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n(\{[\s\S]*?\"workouts\"\s*:\s*\[[\s\S]*?\][\s\S]*?\})\s*```",
    re.IGNORECASE,
)
_BARE_WORKOUTS_JSON_RE = re.compile(
    r"(\{\s*\"workouts\"\s*:\s*\[[\s\S]*?\]\s*\})",
    re.IGNORECASE,
)
_WORKOUT_REMOVAL_RE = re.compile(
    r"```(?:json\s+)?workout_removal\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
_TYPE_UPDATE_RE = re.compile(
    r"```(?:json\s+)?athlete_type_update\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
_AGREEMENTS_UPDATE_RE = re.compile(
    r"```(?:json\s+)?agreements_update\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
_PLAN_UPDATE_RE = re.compile(
    r"```(?:json\s+)?plan_update\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
# One-shot: save planned_sessions + push same session to Intervals.
# Deliberately does NOT match bare «ja sync» / «ok sync» (those are plan-sync follow-ups).
_CONFIRM_AND_PUSH_RE = re.compile(
    r"^\s*(?:"
    r"bekreft\s+og\s+(?:push|synk|sync|lagre)(?:\s+(?:til|på|i)\s+(?:intervals|icu))?|"
    r"(?:lagre|push)\s+og\s+(?:push|synk|sync|bekreft)(?:\s+(?:til|på|i)\s+(?:intervals|icu))?|"
    r"ja[,]?\s+lagre\s+og\s+(?:push|synk|sync)(?:\s+(?:til|på|i)\s+(?:intervals|icu))?|"
    r"bekreft\s+(?:og\s+)?push\s+til\s+intervals"
    r")\s*[!.?]*\s*$",
    re.IGNORECASE,
)


def _athlete_knowledge_draft(athlete: dict[str, Any]) -> dict[str, Any]:
    """Map persisted athlete → draft shape for adaptive knowledge selection."""
    return {
        "goal_text": athlete.get("goal_text") or "",
        "injury_notes": athlete.get("injury_notes") or "",
        "schedule_notes": athlete.get("schedule_notes") or "",
        "background_notes": athlete.get("notes") or "",
        "notes": athlete.get("notes") or "",
        "coach_respect_notes": athlete.get("coach_style_note") or "",
        "fitness_notes": athlete.get("fitness_notes") or "",
        "athlete_type": athlete.get("athlete_type") or "",
        "allowed_disciplines": athlete.get("allowed_disciplines") or [],
        "sessions_per_week": athlete.get("sessions_per_week"),
        "agreements": athlete.get("agreements") or [],
        "goal_race_date": athlete.get("goal_race_date"),
        "weekly_hours_target": athlete.get("weekly_hours_target"),
        "username": athlete.get("username") or "",
        "id": athlete.get("id") or "",
        "athlete_id": athlete.get("id") or "",
    }


def _athlete_query_blob(athlete: dict[str, Any], extra: str = "") -> str:
    parts = [
        str(athlete.get("goal_text") or ""),
        str(athlete.get("injury_notes") or ""),
        str(athlete.get("schedule_notes") or ""),
        str(athlete.get("fitness_notes") or ""),
        str(athlete.get("notes") or ""),
        str(athlete.get("athlete_type") or ""),
        str(athlete.get("sessions_per_week") or ""),
        " ".join(str(a) for a in (athlete.get("agreements") or [])),
        extra or "",
    ]
    return " ".join(p for p in parts if p)


def session_thread_memory(
    history: list[dict[str, Any]] | None,
    *,
    max_lines: int = 8,
) -> str:
    """Compact in-session agreements / decisions from recent turns (multi-turn memory)."""
    lines: list[str] = []
    for msg in reversed(list(history or [])[-20:]):
        role = (msg.get("role") or "").strip()
        text = (msg.get("content") or "").strip()
        if not text or role not in ("user", "assistant"):
            continue
        low = text.lower()
        if not re.search(
            r"\bavtal(?:t|er|e)\b|\bvi\s+tar\b|\bok[,]?\s+da\b|"
            r"sessions_per_week|økter/uke|måldato|ikke\s+rør|"
            r"don'?t\s+touch|plan\s*b|ukerisiko|ftp\s*\d+",
            low,
        ):
            continue
        who = "Utøver" if role == "user" else "Trener"
        compact = strip_workout_json_from_prose(text).replace("\n", " ")
        compact = re.sub(r"\s+", " ", compact).strip()[:220]
        if compact:
            lines.append(f"- {who}: {compact}")
        if len(lines) >= max_lines:
            break
    if not lines:
        return "(ingen ekstra tråd-avtaler i denne chatten ennå)"
    lines.reverse()  # chronological
    return "\n".join(lines)


def build_system_prompt(
    athlete: dict[str, Any],
    knowledge_dir,
    overview_stub: dict[str, Any] | None = None,
    athletes_dir: Path | None = None,
    *,
    query_text: str = "",
    focused_session: dict[str, Any] | None = None,
    user_message: str = "",
    history: list[dict[str, Any]] | None = None,
) -> str:
    """Single coach system prompt for main chat and Økter detail chat.

    Session focus only extends knowledge retrieval + a few regler bullets —
    no separate prompt builder. Honest voice via HONEST_COACH_VOICE.
    """
    personality = (athlete.get("coach_personality") or "direkte").strip().lower()
    # Prefer OPV lean for default/direkte — closer to agent-modus.
    if personality in ("direkte", "opv", ""):
        hint = PERSONALITY_HINTS["opv"]
    else:
        hint = PERSONALITY_HINTS.get(personality, PERSONALITY_HINTS["opv"])
    coach = athlete.get("coach_display_name") or "Trener"
    name = athlete.get("display_name") or "utøveren"
    # Never Path(".") — that can pick up another athlete's on-disk profile by accident.
    # Incomplete athletes get SQLite/render only; no seeded William / docs/athlete fallback.
    profile_md = load_profile_md(athletes_dir, athlete)
    # Prefer explicit focused_session; else peek overview stub
    focused = focused_session
    if focused is None and isinstance(overview_stub, dict):
        focused = overview_stub.get("focused_session")
    draft = _athlete_knowledge_draft(athlete)
    q = (query_text or "").strip() or session_query_text(
        focused, user_message=user_message
    ) or _athlete_query_blob(athlete)
    knowledge = load_knowledge_bundle(
        knowledge_dir,
        query_text=q or " ",
        draft=draft,
        focused_session=focused,
        mode="chat",
        total_budget=6500,
    )
    overview_json = json.dumps(overview_stub or {}, ensure_ascii=False)
    atype = athlete.get("athlete_type") or "(ikke satt)"
    sess = athlete.get("sessions_per_week")
    sess_line = f"{sess} økter/uke" if sess else "(ikke avtalt)"
    agreements = athlete.get("agreements") or []
    agr_line = "; ".join(str(a) for a in agreements[:12]) if agreements else "(ingen)"
    thread_mem = session_thread_memory(history)
    if focused:
        focused_bullets = (
            "- focused_session i snapshot: utøveren er i økt-detalj. Svar om DEN økten. "
            "Ved eksplisitt endring: workout_proposal med Warmup/Main/Cooldown + Plan B.\n"
            "- Hardere/lengre enn knowledge/skade tillater → nei + bedre alternativ.\n"
        )
    else:
        focused_bullets = (
            "- Hvis focused_session finnes: hold fokus på den økten til utøveren bytter tema.\n"
        )

    return f"""Du er {coach}, personlig utholdenhetstrener for {name}.
Språk: norsk. Tone: {hint}
{HONEST_COACH_VOICE}
Stil-notat: {athlete.get("coach_style_note") or "(ingen)"}
Profiltype: {atype} | Frekvens: {sess_line} | Avtaler: {agr_line}
Tråd-minne (denne chatten — husk og bygg videre, ikke spør om igjen):
{thread_mem}

Kjerne:
- Én anbefaling. Målrealisme før PB-løfter. Pushback på 2019-volum / for hard kvalitet / skadesignaler.
- Anta ikke Williams historikk / Lofoten 2027 / 750t med mindre profilen eller seeded data har det.
- app_plan i snapshot = lagret plan. Når has_plan: ikke late som du «ikke har spesifisert økter».
- «Hva har jeg denne uka?» → sessions.planlagt/today/upcoming. «Hva har jeg gjort?» → kun gjennomført (ICU).
- Respekter allowed_disciplines + sessions_per_week + skadenotat.
{focused_bullets}
{_WRITE_PROTOCOL_NB}

## Profil
{profile_md}

## Overblikk-snapshot (JSON)
{overview_json}

## Knowledge (trimmet, adaptiv)
{knowledge}
"""


def workout_proposal_history_summary(proposal: dict[str, Any] | None) -> str:
    """Compact structure lines for chat history (no JSON) so reopen/one-shot recover."""
    workouts = (proposal or {}).get("workouts") or []
    if not workouts:
        return ""
    lines: list[str] = []
    for w in workouts[:4]:
        if not isinstance(w, dict):
            continue
        name = str(w.get("name") or "Økt").strip()
        date_s = str(w.get("date") or "")[:10]
        sport = str(w.get("sport") or "").strip()
        dur = w.get("duration_minutes")
        bits = [b for b in (date_s, name, sport) if b]
        if dur is not None:
            bits.append(f"{dur} min")
        lines.append(" · ".join(bits))
        desc = strip_workout_json_from_prose(str(w.get("description") or "")).strip()
        if desc and '"workouts"' not in desc:
            for dl in desc.splitlines()[:8]:
                if dl.strip():
                    lines.append(dl.strip())
        steps = w.get("steps")
        if isinstance(steps, list) and steps and not desc:
            for s in steps[:12]:
                if not isinstance(s, dict):
                    continue
                st = s.get("type") or "work"
                sd = s.get("duration_minutes")
                si = s.get("intensity") or ""
                lines.append(
                    f"- {st}"
                    + (f" {sd} min" if sd else "")
                    + (f" {si}" if si else "")
                )
    if not lines:
        return ""
    return (
        "Struktur for bekreftelseskortet (Forhåndsvis → Ja, eller one-shot lagre+ICU):\n"
        + "\n".join(lines)
    )


def knowledge_meta_for_chat(
    knowledge_dir,
    *,
    athlete: dict[str, Any] | None = None,
    focused_session: dict[str, Any] | None = None,
    user_message: str = "",
) -> dict[str, Any]:
    """Public meta for API responses / tests (paths used for this turn)."""
    draft = _athlete_knowledge_draft(athlete) if athlete else None
    return knowledge_selection_meta(
        knowledge_dir,
        query_text=session_query_text(focused_session, user_message=user_message)
        or " ",
        draft=draft,
        focused_session=focused_session,
        mode="chat",
    )


def _clean_workout_dicts(workouts: list[Any]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for w in workouts:
        if not isinstance(w, dict):
            continue
        name = str(w.get("name") or "").strip()
        date_s = str(w.get("date") or "").strip()[:10]
        if not name or not date_s:
            continue
        sport = str(w.get("sport") or w.get("type") or "other").strip().lower()
        dur = w.get("duration_minutes")
        try:
            dur_i = int(float(dur)) if dur is not None and str(dur).strip() else None
        except (TypeError, ValueError):
            dur_i = None
        start = str(w.get("start_time") or "07:00").strip() or "07:00"
        desc = strip_workout_json_from_prose(str(w.get("description") or "")).strip()[:2000]
        # Never keep raw JSON blobs as the Intervals description.
        if desc.lstrip().startswith("{") and '"workouts"' in desc:
            desc = ""
        row: dict[str, Any] = {
            "name": name[:120],
            "date": date_s,
            "sport": sport,
            "duration_minutes": dur_i,
            "description": desc,
            "start_time": start[:5],
        }
        steps = w.get("steps") or w.get("steps_json")
        if isinstance(steps, list) and steps:
            row["steps"] = steps
        elif isinstance(steps, str) and steps.strip().startswith("["):
            try:
                parsed = json.loads(steps)
                if isinstance(parsed, list) and parsed:
                    row["steps"] = parsed
            except json.JSONDecodeError:
                pass
        cleaned.append(row)
    return cleaned


def strip_workout_json_from_prose(text: str) -> str:
    """Remove workout_proposal fences / bare workouts JSON from assistant prose.

    Prefer the UI card — athletes must not see raw JSON in chat.
    """
    if not text:
        return ""
    out = _WORKOUT_PROPOSAL_RE.sub("", text)
    out = _GENERIC_WORKOUTS_FENCE_RE.sub("", out)
    out = _BARE_WORKOUTS_JSON_RE.sub("", out)
    out = _WORKOUT_REMOVAL_RE.sub("", out)
    out = _TYPE_UPDATE_RE.sub("", out)
    out = _AGREEMENTS_UPDATE_RE.sub("", out)
    out = _PLAN_UPDATE_RE.sub("", out)
    # Orphan fence openers left after partial strip
    out = re.sub(r"```(?:json\s+)?workout_proposal\s*", "", out, flags=re.IGNORECASE)
    out = re.sub(r"```+", "", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _parse_workouts_json_blob(raw: str) -> list[dict[str, Any]] | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Tolerate trailing commas / single quotes lightly — fail closed.
        return None
    if not isinstance(data, dict):
        return None
    workouts = data.get("workouts")
    if not isinstance(workouts, list) or not workouts:
        return None
    cleaned = _clean_workout_dicts(workouts)
    return cleaned or None


def extract_workout_proposal(reply: str) -> tuple[str, dict[str, Any] | None]:
    """Strip optional workout_proposal fence; return (display_text, proposal|None)."""
    if not reply:
        return "", None
    cleaned_workouts: list[dict[str, Any]] | None = None
    match = _WORKOUT_PROPOSAL_RE.search(reply)
    if match:
        cleaned_workouts = _parse_workouts_json_blob(match.group(1) or "")
    if cleaned_workouts is None:
        gen = _GENERIC_WORKOUTS_FENCE_RE.search(reply)
        if gen:
            cleaned_workouts = _parse_workouts_json_blob(gen.group(1) or "")
    if cleaned_workouts is None:
        bare = _BARE_WORKOUTS_JSON_RE.search(reply)
        if bare:
            cleaned_workouts = _parse_workouts_json_blob(bare.group(1) or "")

    display = strip_workout_json_from_prose(reply)
    if not cleaned_workouts:
        # Always strip JSON-looking fences from display even when parse failed.
        return display or reply.strip(), None
    return display or (
        "Her er forslaget — bekreft i appen for å lagre i planen "
        "(deretter Sync til Intervals)."
    ), {"workouts": cleaned_workouts}


_SESSION_INTENT_RE = re.compile(
    r"(?:"
    r"legg\s+(?:inn|til|på)|"
    r"planlegg|book(?:e)?|"
    r"opprett|"
    # «lag» and «lage» (William: «kan du lage en økt for i morgen»)
    r"lag(?:e)?\s+(?:en\s+|ei\s+|ett\s+)?(?:økt|trening|pass)|"
    r"kan\s+du\s+lag(?:e)?|"
    r"foreslå\s+(?:en\s+)?(?:økt|trening)|"
    r"sett\s+inn|"
    r"putt\s+på|"
    r"kan\s+du\s+legge|"
    r"add\s+(?:a\s+)?(?:workout|session)|"
    r"schedule|"
    r"create\s+(?:a\s+)?workout|"
    r"make\s+(?:a\s+)?(?:workout|session)"
    r")",
    re.IGNORECASE,
)

_PLAN_ADJUST_INTENT_RE = re.compile(
    r"(?:"
    r"lett(?:e)?\s+(?:denne\s+)?uk(?:a|en)|"
    r"lette\s+uk(?:a|en)|"
    # «lett uke» / «ha en lett uke» / «sliten — lett uke» (QA prose-only gap)
    r"(?:ha\s+(?:en\s+)?)?lett\s+uke|"
    r"lette?\s+(?:neste\s+)?(?:økter|okter)|"
    r"ease\s+(?:the\s+)?week|"
    # «juster (denne/neste) uka/uken», «bygg om uka», «erstatt hele uka»
    r"jus?etr\s+(?:(?:denne|neste)\s+)?(?:planen|uk(?:a|en)|grovplanen|helg(?:a|en)?)|"
    r"juster\s+(?:(?:denne|neste)\s+)?(?:planen|uk(?:a|en)|grovplanen|helg(?:a|en)?)|"
    r"bygg\s+om\s+(?:(?:denne|neste)\s+)?(?:planen|uk(?:a|en)|grovplanen)|"
    r"endre\s+(?:(?:denne|neste)\s+)?(?:planen|grovplanen|uk(?:a|en)|helg(?:a|en)?|fre|lør)|"
    r"oppdater\s+(?:(?:denne|neste)\s+)?(?:planen|uk(?:a|en)|helg(?:a|en)?|fre|lør|søn)|"
    r"erstatt(?:e)?\s+(?:hele\s+)?(?:denne\s+|neste\s+)?uk(?:a|en)|"
    r"ny\s+(?:ukeplan|grovplan)|"
    r"rebuild\s+(?:plan|week)|"
    # Day swap / move session day (tirsdag → onsdag) — must open week confirm card
    r"(?:bytt(?:e)?|flytt(?:e)?|mov(?:e)?)\s+"
    r"(?:(?:økt(?:a|en)?|trening(?:en)?|pass(?:et)?)\s+)?"
    r"(?:fra\s+)?"
    r"(?:man(?:dag)?|tir(?:sdag)?|ons(?:dag)?|tor(?:sdag)?|fre(?:dag)?|"
    r"lør(?:dag)?|søn(?:dag)?|monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday)"
    r".{0,40}"
    r"(?:→|->|til|to)\s+"
    r"(?:man(?:dag)?|tir(?:sdag)?|ons(?:dag)?|tor(?:sdag)?|fre(?:dag)?|"
    r"lør(?:dag)?|søn(?:dag)?|monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday)|"
    # Multi-day / weekend (fre–lør / helg) without requiring «planen»
    r"(?:juster|endre|oppdater|lette?)\s+"
    r"(?:fre(?:dag)?|lør(?:dag)?|søn(?:dag)?|helg(?:a|en)?)"
    r"(?:\s*(?:[-–og,&/]|til|og)\s*"
    r"(?:fre(?:dag)?|lør(?:dag)?|søn(?:dag)?|helg(?:a|en)?))?|"
    r"(?:fre|lør|søn|fredag|lørdag|søndag)\s*[-–]\s*"
    r"(?:fre|lør|søn|fredag|lørdag|søndag)|"
    # Build / show a week plan from SoT (not a generic interview).
    r"lag(?:e)?\s+(?:en\s+)?(?:plan|ukeplan)|"
    r"planlegg(?:e)?\s+(?:en\s+)?(?:plan|ukeplan|uke)|"
    r"plan\s+for\s+(?:denne|neste)\s+uke|"
    r"(?:denne|neste)\s+uke(?:s)?plan|"
    r"ukeplan\s+for\s+(?:denne|neste)\s+uke"
    r")",
    re.IGNORECASE,
)

_PLAN_WEEK_BUILD_RE = re.compile(
    r"(?:"
    r"lag(?:e)?\s+(?:en\s+)?(?:plan|ukeplan)|"
    r"planlegg(?:e)?\s+(?:en\s+)?(?:plan|ukeplan|uke)|"
    r"plan\s+for\s+(?:denne|neste)\s+uk(?:e|a|en)|"
    r"(?:denne|neste)\s+uke(?:s)?plan|"
    r"ukeplan\s+for\s+(?:denne|neste)\s+uk(?:e|a|en)|"
    # Explicit week replace/rebuild (confirm card, not prose list)
    r"erstatt(?:e)?\s+(?:hele\s+)?(?:denne\s+|neste\s+)?uk(?:a|en)|"
    r"bygg\s+om\s+(?:(?:denne|neste)\s+)?uk(?:a|en)"
    r")",
    re.IGNORECASE,
)

# «ikke rør kalender / ikke synce» — never auto-bulk Intervals
_DONT_TOUCH_CALENDAR_RE = re.compile(
    r"(?:"
    r"ikke\s+(?:rør|endre|oppdater|synce?|pushe?|touch).{0,40}"
    r"(?:kalender|intervals|icu|planen\s+på\s+intervals)|"
    r"(?:don't|do\s+not)\s+touch\s+(?:the\s+)?calendar|"
    r"bare\s+lagre(?:\s+(?:i|til)\s+(?:appen|planen))?|"
    r"uten\s+(?:å\s+)?(?:synce?|pushe?|oppdatere\s+intervals)|"
    r"ingen\s+(?:sync|synk|push)\s+(?:til\s+)?(?:intervals|icu)|"
    r"ikke\s+(?:sync|synk|push)\s+(?:til\s+)?(?:intervals|icu)"
    r")",
    re.IGNORECASE,
)

# Coach-review of Intervals calendar — read/merge only, never push
_INTERVALS_REVIEW_RE = re.compile(
    r"(?:"
    r"(?:sjekk|se\s+over|gjennomgå|review|vurder|analyser).{0,50}"
    r"(?:intervals|icu|kalender(?:en)?)|"
    r"(?:hva\s+ligger|vis\s+(?:meg\s+)?(?:hva\s+som\s+er)).{0,40}"
    r"(?:på\s+)?(?:intervals|icu|kalender(?:en)?)|"
    r"(?:intervals|icu).{0,30}"
    r"(?:kalender|uke|events?|forslag|utkast)|"
    r"coach[- ]?review.{0,20}(?:intervals|icu|kalender)|"
    # App SoT vs ICU truth
    r"sammenlign(?:e)?.{0,40}(?:app|plan|intervals|icu|kalender)|"
    r"(?:app|planen?).{0,20}(?:vs|mot).{0,20}(?:intervals|icu|kalender)|"
    r"(?:intervals|icu).{0,20}(?:vs|mot).{0,20}(?:app|plan)|"
    r"kalender[- ]?sannhet|"
    r"avvik.{0,30}(?:kalender|intervals|icu|plan)"
    r")",
    re.IGNORECASE,
)

# Sunday ukesopp / weekly review (OPV-style structured questions)
_UKESOPP_RE = re.compile(
    r"(?:"
    r"ukesopp|uke\s*[- ]?opp|"
    r"søndags?(?:oppsummering|review|sjekk)|"
    r"weekly\s*review|"
    r"oppsummer\s+(?:uka|uken|denne\s+uka)|"
    r"hvordan\s+(?:gikk|var)\s+(?:uka|uken)"
    r")",
    re.IGNORECASE,
)

# US-1 / Copilot: analyse past week — activities + wellness + planned vs done
_WEEK_CHECK_RE = re.compile(
    r"(?:"
    r"sjekk\s+(?:uka|uken)\s*(?:mi|min)?|"
    r"sjekk\s+(?:denne\s+)?(?:uka|uken)|"
    r"analyser?\s+(?:uka|uken)|"
    r"ukeanalyse|"
    r"hva\s+har\s+jeg\s+gjort\s+(?:denne\s+)?(?:uka|uken)|"
    r"hvordan\s+ser\s+(?:uka|uken)\s+(?:mi|min)\s+ut|"
    r"check\s+(?:my\s+)?week|"
    r"week\s+check|"
    r"analyze\s+(?:my\s+)?week"
    r")",
    re.IGNORECASE,
)

# Sunday / agent coach-rapport (TB markdown) — not ukesopp questions
_COACH_REPORT_RE = re.compile(
    r"(?:"
    r"coach[- ]?rapport|"
    r"tb[- ]?(?:score\s+)?rapport|"
    r"søndagsrapport|"
    r"readiness[- ]?rapport|"
    r"generer\s+(?:coach[- ]?)?rapport|"
    r"vis\s+(?:meg\s+)?(?:tb|readiness|coach[- ]?rapport)|"
    r"sunday\s+report|"
    r"coach\s+report"
    r")",
    re.IGNORECASE,
)

# Intervals → TP file export (zip / ZWO) — never TP write API
_TP_EXPORT_RE = re.compile(
    r"(?:"
    r"eksport(?:er)?\s+(?:til\s+)?(?:tp|training\s*peaks)|"
    r"(?:intervals|icu).{0,30}(?:til|→|->)\s*(?:tp|training\s*peaks)|"
    r"(?:tp|training\s*peaks).{0,20}(?:eksport|export|zip|zwo)|"
    r"last\s+ned\s+(?:tp[- ]?)?(?:zip|zwo|eksport)|"
    r"export\s+(?:to\s+)?(?:tp|trainingpeaks)|"
    r"tp[- ]?from[- ]?intervals"
    r")",
    re.IGNORECASE,
)

# Thin: «hva mangler jeg» → compliance focus (week missed list)
_COMPLIANCE_GAP_RE = re.compile(
    r"(?:"
    r"hva\s+mangler\s+jeg|"
    r"hvilke\s+økter\s+(?:mangler|har\s+jeg\s+ikke)|"
    r"ikke\s+gjennomført|"
    r"planlagt\s+vs\s+(?:gjort|gjennomført|logget)|"
    r"compliance\s+(?:denne\s+)?(?:uka|uken)|"
    r"missed\s+sessions?"
    r")",
    re.IGNORECASE,
)

# Sync existing app plan → Intervals (not invent a new week).
_INTERVALS_PLAN_SYNC_INTENT_RE = re.compile(
    r"(?:"
    r"(?:legg\s+(?:inn|til|på)\s+(?:resten\s+av\s+)?(?:planen|øktene|uka|dette|denne|forslaget)|"
    r"synk(?:e|roniser)?\s+(?:resten\s+av\s+)?(?:planen|øktene|dette|denne)|"
    r"push(?:e)?\s+(?:resten\s+av\s+)?(?:planen|øktene|dette|denne)|"
    r"send\s+(?:resten\s+av\s+)?(?:planen|øktene|dette|denne)|"
    r"oppdater\s+(?:resten\s+av\s+)?(?:planen|øktene|uka|dette|denne|forslaget|det)?)"
    r".{0,40}?"
    r"(?:intervals|icu)|"
    r"(?:intervals|icu).{0,40}?"
    r"(?:legg\s+(?:inn|til|på)|synk|push|send|oppdater).{0,40}?"
    r"(?:planen|øktene|resten|dette|denne|forslaget)?|"
    r"sync\s+(?:the\s+)?plan\s+(?:to\s+)?intervals|"
    r"push\s+(?:the\s+)?plan\s+to\s+intervals|"
    r"put\s+(?:the\s+)?(?:rest\s+of\s+(?:the\s+)?)?plan\s+(?:on|into|in)\s+intervals|"
    # Short / English sync phrases (Kent: «sync til intervals»)
    r"(?:kjør\s+)?(?:sync|synk)(?:\s+til)?\s+(?:intervals|icu)|"
    r"(?:sync|synk)\s+(?:nå|planen|øktene|resten)|"
    r"push\s+(?:til|to)\s+(?:intervals|icu)|"
    # «oppdater (dette) til intervals» / «oppdater intervals»
    r"oppdater(?:\s+(?:dette|denne|forslaget|planen|øktene|det))?\s+"
    r"(?:til|på|i)\s+(?:intervals|icu)|"
    r"oppdater\s+(?:intervals|icu)"
    r")",
    re.IGNORECASE | re.DOTALL,
)

# Follow-up after coach already offered Sync / write preview («sync», «go», «ja», «ok»).
# Also: «det ser bra ut», «ok sync», «lagre» — live transcript confirm phrases.
_SYNC_CONFIRM_FOLLOWUP_RE = re.compile(
    r"^\s*(?:"
    r"sync|synk|go|kjør|"
    r"ok(?:ay)?\s*(?:sync|synk|go)?|"
    r"ja(?:\s*,?\s*(?:takk|sync|synk|gjør\s+det|push|bekreft|oppdater|lagre))?|"
    r"bekreft(?:\s+sync)?|"
    r"gjør\s+det|"
    r"push\s+det|"
    r"oppdater(?:\s+det)?|"
    r"lagre(?:\s+det)?|"
    r"(?:det\s+)?ser\s+(?:bra|fint|godt)\s+ut|"
    r"ser\s+(?:bra|fint|godt)\s+ut|"
    r"yes|"
    r"do\s+it"
    r")\s*[!.?]*\s*$",
    re.IGNORECASE,
)

_ASSISTANT_SYNC_OFFER_MARKERS = (
    "nærvindu",
    "sync-forhåndsvis",
    "bekreft sync",
    "bekreft sync-forhåndsvisningen",
    "synker ikke hele horisonten",
    "planned_sessions",
    "intervals er ikke koblet",
    "første 2 uker",
    "icu_sync",
    "workouts fra lagrede",
    "fra lagrede planned_sessions",
    "synke nærvinduet",
    "koble intervals",
    "intervals_sync_intent",
    "skal jeg synce",
    "skal jeg pushe",
    "vil du at jeg synker",
    "vil du at jeg pusher",
)

# Assistant offered a confirmable write (workout / week) — «ok» must not invent success.
_ASSISTANT_WRITE_OFFER_MARKERS = (
    "bekreft",
    "forhåndsvis",
    "legger jeg det inn",
    "legger jeg inn",
    "så legger jeg",
    "når du bekrefter",
    "trykk ja",
    "workout_proposal",
    "plan_update",
    "warmup",
    "oppvarming",
    "hoveddel",
    "nedkjøling",
    "cooldown",
    "varighet",
    "duration_minutes",
)

_WRITE_SUCCESS_CLAIM_RE = re.compile(
    r"(?:"
    r"jeg\s+har\s+(?:nå\s+)?(?:oppdatert|synket|pushet|lagt\s+inn|lagret|skrevet)|"
    r"(?:økten|øktene|planen|endringen|endringene)\s+(?:er|ble)\s+"
    r"(?:nå\s+)?(?:oppdatert|synket|lagt\s+inn|lagret|på\s+plass)|"
    r"(?:ligger|står)\s+nå\s+(?:i|på)\s+intervals|"
    r"er\s+(?:nå\s+)?(?:synket|pushet|lagt\s+inn)\s+(?:til|i|på)\s+intervals|"
    r"ferdig\s+(?:oppdatert|synket)|"
    r"i'?ve\s+(?:updated|synced|pushed|saved)|"
    r"(?:it'?s|workouts?\s+are)\s+(?:now\s+)?(?:in|on)\s+intervals|"
    r"manuelt\s+i\s+intervals|"
    r"rediger(?:e)?\s+(?:det\s+)?manuelt\s+(?:i|på)\s+intervals|"
    r"gå\s+inn\s+i\s+intervals\s+og\s+(?:legg|endre|oppdater)"
    r")",
    re.IGNORECASE,
)

_HONEST_NO_WRITE_YET_NB = (
    "Ingenting er lagret eller synket ennå. "
    "Bruk forhåndsvisningskortet → bekreft (app-plan først; Intervals kun via Sync). "
    "Jeg synker ikke selv, og jeg ber deg ikke redigere Intervals manuelt når API-et finnes."
)

_SPORT_WORD_RE = re.compile(
    r"\b(svøm(?:me|ming|tur)?|swim|syk(?:kel|le|ling)?|bike|cycling|"
    r"løp(?:e|etur|ing)?|run(?:ning)?|jogge|styrke|strength|"
    r"yoga|ski|row|roing)\b",
    re.IGNORECASE,
)

_DURATION_RE = re.compile(
    r"(\d{1,3})\s*(?:min(?:utt(?:er)?)?|m\b)",
    re.IGNORECASE,
)

_ISO_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")

_LABELED_FIELD_RE = re.compile(
    r"\*\*\s*(?:Økt|Navn|Dato|Varighet|Sport|Disiplin|Beskrivelse)\s*:?\s*\*\*\s*:?\s*([^\n*]+)",
    re.IGNORECASE,
)


def user_requests_intervals_plan_sync(message: str) -> bool:
    """True when athlete asks to push/sync the *existing* plan into Intervals.

    Distinct from adding one new workout or rebuilding the plan.
    """
    text = (message or "").strip()
    if not text:
        return False
    return bool(_INTERVALS_PLAN_SYNC_INTENT_RE.search(text))


def assistant_offered_intervals_sync(
    recent_messages: list[dict[str, Any]] | None,
) -> bool:
    """True when a recent assistant turn already offered Intervals near-window sync."""
    for msg in reversed(list(recent_messages or [])[-6:]):
        if (msg.get("role") or "") != "assistant":
            continue
        text = (msg.get("content") or "").lower()
        if any(marker in text for marker in _ASSISTANT_SYNC_OFFER_MARKERS):
            return True
        # Only inspect the latest assistant turn for confirm follow-ups.
        return False
    return False


def user_confirms_intervals_plan_sync(
    message: str,
    recent_messages: list[dict[str, Any]] | None = None,
) -> bool:
    """True for short «sync»/«go»/«ja» after coach already offered Sync preview.

    Kent regression: coach correctly described near-window, then «sync»/«go»
    must reopen real ``intervals_pending`` — never invent workout JSON.
    """
    text = (message or "").strip()
    if not text:
        return False
    if user_requests_intervals_plan_sync(text):
        return True
    if not _SYNC_CONFIRM_FOLLOWUP_RE.match(text):
        return False
    return assistant_offered_intervals_sync(recent_messages)


def _latest_assistant_text(
    recent_messages: list[dict[str, Any]] | None,
) -> str:
    for msg in reversed(list(recent_messages or [])[-8:]):
        if (msg.get("role") or "") == "assistant" and (msg.get("content") or "").strip():
            return str(msg.get("content") or "")
    return ""


def assistant_offered_write_confirm(
    recent_messages: list[dict[str, Any]] | None,
) -> bool:
    """True when latest assistant turn offered a confirmable write (not yet synced)."""
    text = _latest_assistant_text(recent_messages).lower()
    if not text:
        return False
    if any(marker in text for marker in _ASSISTANT_WRITE_OFFER_MARKERS):
        return True
    # Structured prose (date + duration + sport) without fence still counts.
    if _ISO_DATE_RE.search(text) and _DURATION_RE.search(text) and _SPORT_WORD_RE.search(
        text
    ):
        return True
    if _relative_date_hint(text) and _DURATION_RE.search(text):
        return True
    return False


def _relative_date_hint(text: str) -> bool:
    raw = (text or "").lower()
    return bool(
        re.search(
            r"\bi\s+morgen\b|\btomorrow\b|\bi\s+dag\b|\btoday\b|"
            r"\b(?:mandag|tirsdag|onsdag|torsdag|fredag|lørdag|søndag|"
            r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            raw,
        )
    )


def user_confirms_pending_write(
    message: str,
    recent_messages: list[dict[str, Any]] | None = None,
) -> bool:
    """True for short «ok»/«ja»/«oppdater» after coach offered a write card/prose.

    Must never reach the LLM as «jeg har oppdatert» — reopen proposal or sync.
    """
    text = (message or "").strip()
    if not text:
        return False
    if user_requests_confirm_and_push(text):
        return False
    # Explicit sync phrases are handled by intervals path, not this helper.
    if user_requests_intervals_plan_sync(text):
        return False
    if user_requests_session_change(text) or user_requests_plan_adjust(text):
        return False
    if not _SYNC_CONFIRM_FOLLOWUP_RE.match(text):
        return False
    if assistant_offered_intervals_sync(recent_messages):
        return False  # sync confirm path owns these
    return assistant_offered_write_confirm(recent_messages)


def sanitize_unconfirmed_write_claims(
    reply: str,
    *,
    has_confirm_card: bool,
) -> str:
    """Strip/block success claims when no preview→confirm card is attached.

    Fail closed: never let prose say workouts are in Intervals/app without a card.
    """
    text = (reply or "").strip()
    if not text:
        return text
    if has_confirm_card:
        # Even with a card, kill premature «already synced» / «edit manually» lines.
        if not _WRITE_SUCCESS_CLAIM_RE.search(text):
            return text
        cleaned = _WRITE_SUCCESS_CLAIM_RE.sub("", text)
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"\.\s*\.", ".", cleaned)
        cleaned = cleaned.strip(" \t\n.")
        if cleaned and "forhåndsvis" not in cleaned.lower() and "bekreft" not in cleaned.lower():
            cleaned = (
                f"{cleaned}.\n\n"
                "Ingenting er synket ennå — bruk forhåndsvisningskortet → bekreft."
            )
        return cleaned or (
            "Forslaget er klart. Bekreft i forhåndsvisningskortet — "
            "ingenting er lagret/synket før du trykker Ja."
        )
    if not _WRITE_SUCCESS_CLAIM_RE.search(text):
        # Also catch soft «jeg oppdaterer nå» without the full claim regex
        soft = re.search(
            r"jeg\s+(?:oppdaterer|synker|pusher|legger\s+inn)\s+nå|"
            r"nå\s+er\s+(?:det|økten|planen)\s+(?:i|på)\s+intervals",
            text,
            re.IGNORECASE,
        )
        if not soft:
            return text
    return _HONEST_NO_WRITE_YET_NB


def user_requests_session_change(message: str) -> bool:
    """True when the athlete clearly asks to add/change a concrete session."""
    text = (message or "").strip()
    if not text:
        return False
    # «Legg inn resten av planen i intervals» is plan-sync, not a new session.
    if user_requests_intervals_plan_sync(text):
        return False
    return bool(_SESSION_INTENT_RE.search(text))


def user_requests_plan_adjust(message: str) -> bool:
    """True when the athlete asks to ease/rebuild plan or week."""
    text = (message or "").strip()
    if not text:
        return False
    # Sync-to-Intervals is not a rebuild request.
    if user_requests_intervals_plan_sync(text):
        return False
    return bool(_PLAN_ADJUST_INTENT_RE.search(text))


def user_requests_plan_week_build(message: str) -> bool:
    """True when athlete asks to create/show a week plan (not generic chat)."""
    text = (message or "").strip()
    if not text:
        return False
    if user_requests_intervals_plan_sync(text):
        return False
    return bool(_PLAN_WEEK_BUILD_RE.search(text))


def user_wants_week_rebuild(message: str) -> bool:
    """True when athlete wants to replace/rebuild the week (not just list SoT)."""
    text = (message or "").strip().lower()
    if not text:
        return False
    return bool(
        re.search(
            r"erstatt|bygg\s+om|ny\s+ukeplan|rebuild|"
            r"juster\s+(?:(?:denne|neste)\s+)?uk|"
            r"oppdater\s+(?:(?:denne|neste)\s+)?uk|"
            r"endre\s+(?:(?:denne|neste)\s+)?uk|"
            r"lett(?:e)?\s+(?:(?:denne|neste)\s+)?uk",
            text,
        )
    )


def user_requests_dont_touch_calendar(message: str) -> bool:
    """True when athlete forbids Intervals/calendar writes this turn."""
    text = (message or "").strip()
    if not text:
        return False
    return bool(_DONT_TOUCH_CALENDAR_RE.search(text))


def user_requests_intervals_review(message: str) -> bool:
    """True for coach-review of ICU calendar without push."""
    text = (message or "").strip()
    if not text:
        return False
    if user_requests_intervals_plan_sync(text):
        return False
    if user_requests_confirm_and_push(text):
        return False
    return bool(_INTERVALS_REVIEW_RE.search(text))


def user_requests_ukesopp(message: str) -> bool:
    """True for Sunday ukesopp / weekly review (structured questions)."""
    text = (message or "").strip()
    if not text:
        return False
    if user_requests_intervals_plan_sync(text):
        return False
    if user_requests_confirm_and_push(text):
        return False
    # Prefer deterministic week analysis when phrasing is «sjekk uka mi»
    if user_requests_week_check(text) and not re.search(
        r"ukesopp|uke\s*[- ]?opp|weekly\s*review|søndags?", text, re.I
    ):
        return False
    return bool(_UKESOPP_RE.search(text))


def user_requests_week_check(message: str) -> bool:
    """True for «sjekk uka mi» style analysis (activities + wellness + compliance)."""
    text = (message or "").strip()
    if not text:
        return False
    if user_requests_intervals_plan_sync(text):
        return False
    if user_requests_confirm_and_push(text):
        return False
    return bool(_WEEK_CHECK_RE.search(text))


def user_requests_coach_report(message: str) -> bool:
    """True for Sunday / TB coach-rapport (markdown ritual)."""
    text = (message or "").strip()
    if not text:
        return False
    if user_requests_intervals_plan_sync(text):
        return False
    if user_requests_confirm_and_push(text):
        return False
    # Prefer full week-check when both could match
    if user_requests_week_check(text):
        return False
    return bool(_COACH_REPORT_RE.search(text))


def user_requests_tp_export(message: str) -> bool:
    """True for Intervals→TP zip export (files only, no TP write)."""
    text = (message or "").strip()
    if not text:
        return False
    if user_requests_intervals_plan_sync(text):
        return False
    if user_requests_confirm_and_push(text):
        return False
    return bool(_TP_EXPORT_RE.search(text))


def user_requests_compliance_gap(message: str) -> bool:
    """True for «hva mangler jeg» / planned vs logged focus."""
    text = (message or "").strip()
    if not text:
        return False
    if user_requests_intervals_plan_sync(text):
        return False
    if user_requests_confirm_and_push(text):
        return False
    if user_requests_week_check(text):
        return False
    if user_requests_coach_report(text):
        return False
    return bool(_COMPLIANCE_GAP_RE.search(text))


UKESOPP_QUESTIONS_NB = (
    "Kontinuitet: Hvor mange planlagte økter fullførte du (X/Y)? Hva droppet du?",
    "Belastning: Hvordan føltes totalvolumet (lett / passe / hardt)? Søvn/stress?",
    "Highlight: Én økt som gikk bra — hva var bra?",
    "Justering neste uke: Én ting å skjerpe (eller Plan B hvis uka var rød).",
)


def ukesopp_prompt_payload(
    *,
    week_start: str,
    week_end: str,
    planned_count: int = 0,
    completed_hint: str | None = None,
) -> dict[str, Any]:
    """Structured ukesopp card payload (no Intervals write)."""
    questions = list(UKESOPP_QUESTIONS_NB)
    return {
        "week_start": week_start,
        "week_end": week_end,
        "questions": questions,
        "planned_count": planned_count,
        "completed_hint": completed_hint,
        "confirm_required": False,
        "written_to_intervals": False,
        "can_save_answers": True,
    }


def ukesopp_reply_nb(
    *,
    name: str,
    week_start: str,
    week_end: str,
    planned_count: int = 0,
    session_lines: list[str] | None = None,
    completed_hint: str | None = None,
) -> str:
    """OPV-style ukesopp prompt — questions only, no false write claims."""
    bits = [
        f"Ukesopp {week_start}–{week_end}",
        "",
        f"Hei {name} — svar kort på disse (som søndag hos OPV). "
        "Svarene kan lagres i appen (ikke Intervals) via kortet under.",
        "",
    ]
    if planned_count:
        bits.append(f"App-plan denne uka: {planned_count} økter.")
    if completed_hint:
        bits.append(completed_hint)
    if session_lines:
        bits.append("Planlagt:")
        bits.extend(f"- {ln}" for ln in session_lines[:10])
        bits.append("")
    for i, q in enumerate(UKESOPP_QUESTIONS_NB, 1):
        bits.append(f"{i}. {q}")
    bits.append("")
    bits.append(
        "Når du har svart, kan jeg foreslå justering (preview → bekreft) — "
        "ikke Intervals-push uten at du ber om det."
    )
    return "\n".join(bits)


def coach_report_reply_nb(
    *,
    name: str,
    markdown: str,
    available: bool,
    note: str | None = None,
) -> str:
    """Short chat wrapper around Sunday coach-rapport markdown."""
    bits = [
        f"Hei {name} — coach-rapport (samme motor som agent søndagsritual).",
        "Ingen grafer i web; ingen Intervals-write.",
        "",
    ]
    if not available:
        bits.append(note or "TB-Score ikke tilgjengelig — koble Intervals under Du.")
        bits.append("")
        bits.append("Du kan fortsatt kjøre **ukesopp** eller **sjekk uka mi**.")
        return "\n".join(bits)
    # Keep reply readable in chat; full markdown also in card payload
    body = (markdown or "").strip()
    if len(body) > 3500:
        body = body[:3400].rstrip() + "\n\n… (full tekst i kortet / Dashboard)"
    bits.append(body)
    bits.append("")
    bits.append("Neste: **ukesopp** for spørsmål, eller last ned TP-zip fra Dashboard.")
    return "\n".join(bits)


def tp_export_reply_nb(
    *,
    name: str,
    start: str,
    end: str,
    available: bool,
    meta: dict[str, Any] | None = None,
    note: str | None = None,
) -> str:
    """Explain Intervals→TP zip (manual import, no TP API write)."""
    bits = [
        f"Hei {name} — Intervals → TrainingPeaks eksport ({start} … {end}).",
        "Appen lager **filer** (zip). Ingen auto-write til TrainingPeaks.",
        "",
    ]
    if not available:
        bits.append(note or "Intervals ikke koblet — koble under Du først.")
        return "\n".join(bits)
    m = meta or {}
    bits.append(
        f"Pakke: {m.get('workouts', 0)} økter "
        f"({m.get('zwo', 0)} ZWO, {m.get('strength', 0)} styrke-CSV, "
        f"{m.get('txt_fallback', 0)} tekst-fallback)."
    )
    bits.append("")
    bits.append("Last ned via knappen under / Dashboard «Last ned TP-zip».")
    bits.append(
        "Sykkel: Library → Import `.zwo`. "
        "Løp/svøm: importer som sykkel → Build → bytt sport → % terskel. "
        "Styrke: trainingdojo.app/import."
    )
    bits.append("")
    bits.append(
        "CLI: `python3 scripts/export_intervals_plan_to_tp.py "
        f"--start {start} --end {end}`"
    )
    return "\n".join(bits)


def compliance_gap_reply_nb(
    *,
    name: str,
    week_start: str,
    week_end: str,
    compliance: dict[str, Any],
    intervals_linked: bool,
) -> str:
    """Focused planned-vs-logged reply for Dashboard/chat."""
    bits = [
        f"Hei {name} — planlagt vs logget {week_start}–{week_end}.",
        "",
    ]
    if not intervals_linked:
        bits.append(
            "Intervals er ikke koblet — jeg kan ikke matche WORKOUT mot aktiviteter. "
            "Koble under Du."
        )
        return "\n".join(bits)
    planned = int(compliance.get("sessions_planned") or 0)
    done = int(compliance.get("sessions_done") or 0)
    pct = compliance.get("compliance_pct")
    pct_s = f" ({pct} %)" if pct is not None else ""
    bits.append(f"Økt-compliance: **{done} / {planned}**{pct_s}.")
    bits.append(compliance.get("note_nb") or "")
    bits.append("")
    missed = compliance.get("missed_lines") or []
    bits.append(f"Ikke gjennomført ({len(missed)}):")
    if missed:
        bits.extend(f"- {ln}" for ln in missed[:12])
    else:
        bits.append("- (ingen åpne hull i vinduet)")
    bits.append("")
    done_lines = compliance.get("done_lines") or []
    bits.append(f"Logget ({len(done_lines)}):")
    if done_lines:
        bits.extend(f"- {ln}" for ln in done_lines[:10])
    else:
        bits.append("- (ingen aktiviteter matchet)")
    roll = compliance.get("rolling_compliance_4w") or {}
    if roll.get("sessions_planned"):
        bits.append("")
        bits.append(
            f"4 uker: {roll.get('sessions_done', 0)} / {roll.get('sessions_planned')} "
            f"({roll.get('compliance_pct')} %)."
        )
    bits.append("")
    bits.append("Full analyse: **sjekk uka mi**. Søndag: **coach-rapport** / **ukesopp**.")
    return "\n".join(bits)


def week_check_summary_nb(
    *,
    name: str,
    week_start: str,
    week_end: str,
    planned_lines: list[str],
    completed_lines: list[str],
    missed_lines: list[str],
    wellness_bits: list[str],
    intervals_linked: bool,
    fetch_error: bool = False,
    fetch_detail: str | None = None,
    compliance_pct: float | None = None,
    sessions_planned: int = 0,
    sessions_done: int = 0,
    calendar_source_line: str | None = None,
    load_bits: list[str] | None = None,
    tb_bits: list[str] | None = None,
    plan_b_bits: list[str] | None = None,
    risk_bits: list[str] | None = None,
    prescription_blocks: list[str] | None = None,
) -> str:
    """Deterministic «sjekk uka mi» — agent-modus style: load, TB, Plan B, prescriptions."""
    bits = [
        f"Ukesjekk {week_start}–{week_end}",
        "",
        f"Hei {name}. Planlagt vs gjennomført "
        "(gjennomført = ICU-aktiviteter; NOTE teller ikke).",
        "",
    ]
    if calendar_source_line:
        bits.append(calendar_source_line)
        bits.append("")
    if not intervals_linked:
        bits.append(
            "Intervals er ikke koblet — jeg kan vise app-plan, "
            "men ikke faktisk gjennomført volum. Koble under Du."
        )
        bits.append("")
    elif fetch_error:
        bits.append(
            "Kunne ikke hente Intervals-data"
            + (f" ({fetch_detail})." if fetch_detail else ".")
            + " Viser ikke fake tall — prøv igjen snart."
        )
        bits.append("")

    if sessions_planned or sessions_done:
        pct = f" ({compliance_pct} %)" if compliance_pct is not None else ""
        bits.append(
            f"Økt-compliance denne uka: {sessions_done} / {sessions_planned} "
            f"planlagte WORKOUT matchet til aktivitet{pct}."
        )
        bits.append("")

    if load_bits:
        bits.append("Belastning / intensitet:")
        bits.extend(f"- {b}" for b in load_bits[:6])
        bits.append("")

    if tb_bits:
        bits.append("TB-Score / readiness:")
        bits.extend(f"- {b}" for b in tb_bits[:8])
        bits.append("")

    bits.append(f"Planlagt ({len(planned_lines)}):")
    if planned_lines:
        bits.extend(f"- {ln}" for ln in planned_lines[:12])
    else:
        bits.append("- (ingen planlagte økter i vinduet)")
    bits.append("")
    bits.append(f"Gjennomført / ICU-aktiviteter ({len(completed_lines)}):")
    if completed_lines:
        bits.extend(f"- {ln}" for ln in completed_lines[:12])
    else:
        bits.append("- (ingen aktiviteter i vinduet)")
    bits.append("")
    bits.append(f"Ikke gjennomført ({len(missed_lines)}):")
    if missed_lines:
        bits.extend(f"- {ln}" for ln in missed_lines[:10])
    else:
        bits.append("- (ingen åpne hull)")
    bits.append("")

    if prescription_blocks:
        bits.append("Kvalitetsøkter (full resept — warmup / hoveddel / cooldown):")
        bits.append("")
        for block in prescription_blocks[:4]:
            bits.append(block)
            bits.append("")

    if plan_b_bits:
        bits.append("Plan B:")
        bits.extend(f"- {b}" for b in plan_b_bits[:5])
        bits.append("")
    if risk_bits:
        bits.append("Ukerisiko:")
        bits.extend(f"- {b}" for b in risk_bits[:3])
        bits.append("")

    bits.append("Wellness (signaler, ikke absolutt sannhet):")
    if wellness_bits:
        bits.extend(f"- {b}" for b in wellness_bits[:6])
    else:
        bits.append("- (ingen wellness-data)")
    bits.append("")
    bits.append(
        "Ingen endring lagret. Si «ukesopp» for strukturerte spørsmål, "
        "eller be om justering hvis noe skal endres (preview → bekreft)."
    )
    return "\n".join(bits)


def plan_week_target_from_message(message: str) -> str:
    """``this_week`` or ``next_week`` for week_bounds / week adjust."""
    text = (message or "").lower()
    if re.search(r"neste\s+uk(?:e|a|en)|next\s+week", text):
        return "next_week"
    if re.search(r"denne\s+uk(?:e|a|en)|this\s+week", text):
        return "this_week"
    return "this_week"


def user_requests_confirm_and_push(message: str) -> bool:
    """True for one-shot «bekreft og push til intervals» (save + same-session ICU)."""
    text = (message or "").strip()
    if not text:
        return False
    return bool(_CONFIRM_AND_PUSH_RE.match(text))


def confirm_write_success_reply_nb(
    *,
    saved: int = 0,
    pushed: int = 0,
    names: list[str] | None = None,
) -> str:
    """Coach message after preview→confirm actually persisted (must match toast)."""
    bits: list[str] = []
    if saved:
        bits.append(f"{saved} økt(er) lagret i planen")
    if pushed:
        bits.append(f"{pushed} på Intervals")
    if not bits:
        return "Bekreftet — ingen nye rader ble skrevet."
    sample = ""
    if names:
        shown = ", ".join(n for n in names[:3] if n)
        if shown:
            sample = f" ({shown})"
    return f"Bekreftet: {' · '.join(bits)}{sample}."


def write_intent_kind(message: str) -> str | None:
    """Return 'sync' | 'session' | 'plan' | 'confirm_push' | None."""
    text = (message or "").strip()
    if not text:
        return None
    if user_requests_confirm_and_push(text):
        return "confirm_push"
    if user_requests_intervals_plan_sync(text):
        return "sync"
    if user_requests_session_change(text):
        return "session"
    if user_requests_plan_adjust(text):
        return "plan"
    return None


_AGREEMENT_ACCEPT_RE = re.compile(
    r"(?:"
    r"ok[,]?\s*da\s+tar\s+vi|"
    r"da\s+tar\s+vi|"
    r"vi\s+avtaler|"
    r"avtalt|"
    r"enig|"
    r"ja[,]?\s+(?:til\s+)?(?:\d+\s+økter|fire|tre|to|fem)|"
    r"(?:endre|oppdater)\s+avtal|"
    r"sessions_per_week|"
    r"\d+\s+økter\s*/?\s*uke"
    r")",
    re.IGNORECASE,
)

_PLAN_ROLL_CONTEXT_RE = re.compile(
    r"(?:"
    r"rull|neste\s+måned|detaljplan|forleng|"
    r"plan(?:en|a)?\s+(?:er\s+)?(?:slutt|tom|ferdig)|"
    r"hva\s+nå\s+med\s+planen|bygg\s+videre"
    r")",
    re.IGNORECASE,
)


def user_accepts_agreement_change(message: str) -> bool:
    """True when athlete is confirming a negotiated agreement (keep agreements card)."""
    text = (message or "").strip()
    if not text:
        return False
    return bool(_AGREEMENT_ACCEPT_RE.search(text))


def user_message_is_talk_mode(message: str) -> bool:
    """True when this turn should stay prose-only (no unsolicited write cards)."""
    text = (message or "").strip()
    if not text:
        return True
    if write_intent_kind(text):
        return False
    if user_accepts_agreement_change(text):
        return False
    if user_requests_dont_touch_calendar(text):
        return False
    if user_requests_week_check(text) or user_requests_ukesopp(text):
        return False
    if user_requests_intervals_review(text):
        return False
    if _PLAN_ROLL_CONTEXT_RE.search(text):
        return False
    return True


def should_offer_soft_plan_roll(message: str, *, explicit: bool = False) -> bool:
    """Soft roll cards only on explicit ask or clear plan-roll context — not every chat turn."""
    if explicit:
        return True
    text = (message or "").strip()
    if not text:
        return False
    if user_message_is_talk_mode(text) and not _PLAN_ROLL_CONTEXT_RE.search(text):
        return False
    return bool(_PLAN_ROLL_CONTEXT_RE.search(text) or user_requests_plan_adjust(text))


def reopen_pending_write_reply(
    recent_messages: list[dict[str, Any]] | None,
    *,
    today: date | None = None,
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    """Rebuild proposal from last assistant turn when user says «ok»/«ja».

    Returns (reply, workout_proposal|None, plan_prop|None). Never claims success.
    Card path: clear «use the card» — not contradictory success/failure.
    """
    last = _latest_assistant_text(recent_messages)
    day0 = today or date.today()
    # Prefer extracting a real fence if the model had one in history (rare).
    _disp, fence_wp = extract_workout_proposal(last)
    if fence_wp:
        return (
            "Forslaget ligger i forhåndsvisningskortet under chatten — "
            "trykk Forhåndsvis → Ja for å lagre (og Sync til Intervals om koblet). "
            "Si «bekreft og push til intervals» for å lagre og pushe samme økt i ett steg.",
            fence_wp,
            None,
        )
    _disp, fence_pl = extract_plan_update(last)
    if fence_pl and fence_pl.get("rebuild"):
        return (
            "Planjusteringen ligger i kortet under — bekreft forhåndsvisningen der. "
            "Ingenting er lagret før du trykker Ja på kortet.",
            None,
            fence_pl,
        )
    # Seed a synthetic user message so session-change gate passes.
    # Keep seed free of sync-trigger phrases (those live in the reply body).
    seed = "legg inn økt i morgen"
    if date_s := (_ISO_DATE_RE.search(last) or None):
        seed = f"legg inn økt {date_s.group(1)}"
    inferred = infer_workout_proposal_fallback(seed, last, today=day0)
    if inferred:
        return (
            "Forslaget er i forhåndsvisningskortet under — trykk Forhåndsvis → Ja. "
            "Si «bekreft og push til intervals» for lagring + samme økt til Intervals. "
            "Ingenting er lagret før kortet er bekreftet.",
            inferred,
            None,
        )
    plan_fb = infer_plan_update_fallback("juster uka")
    if last and any(
        m in last.lower()
        for m in ("uke", "helg", "fredag", "lørdag", "plan", "juster")
    ):
        return (
            "Bekreft uke-/planjustering via forhåndsvisningskortet under chatten. "
            "Ingenting er lagret før du trykker Ja.",
            None,
            plan_fb,
        )
    return (_HONEST_NO_WRITE_YET_NB, None, None)


def plan_summary_for_chat(
    athlete: dict[str, Any] | None,
    *,
    planned_sessions: list[dict[str, Any]] | None = None,
    plan_blocks: list[dict[str, Any]] | None = None,
    intervals_connected: bool = False,
    icu_sync_weeks: int = 2,
    max_sample: int = 8,
) -> dict[str, Any]:
    """Compact app-plan SoT for the LLM snapshot — prevents «jeg har ikke spesifisert…».

    Full plan lives in ``planned_sessions``; Intervals only gets the near window.
    """
    rows = list(planned_sessions or [])
    blocks = list(plan_blocks or [])
    ath = athlete or {}
    sess_pw = ath.get("sessions_per_week")
    discs = ath.get("allowed_disciplines") or []
    sample: list[dict[str, Any]] = []
    for r in rows[: max(1, max_sample)]:
        sample.append(
            {
                "date": (r.get("session_date") or r.get("date") or "")[:10],
                "name": (r.get("name") or "")[:80],
                "sport": (r.get("sport") or r.get("discipline") or "")[:40],
                "duration_minutes": r.get("duration_minutes"),
            }
        )
    block_titles = [
        str(b.get("title") or b.get("theme") or "").strip()[:60]
        for b in blocks[:6]
        if str(b.get("title") or b.get("theme") or "").strip()
    ]
    n = len(rows)
    has_plan = n > 0 or bool(blocks)
    note = (
        f"App-plan finnes: {n} planned_sessions"
        + (f", {sess_pw} økter/uke" if sess_pw else "")
        + (f", disipliner {', '.join(str(d) for d in discs[:6])}" if discs else "")
        + f". Intervals WORKOUT-sync = kun første {icu_sync_weeks} uker; "
        "resten av horisonten blir i appen. "
        "Ikke spør om økttyper / ikke finn opp ny ukeplan når planned_sessions finnes."
        if has_plan
        else (
            "Ingen lagret planned_sessions ennå — ikke synce Intervals før setup/confirm "
            "eller plan er lagret. Ikke finn opp en parallell prosa-plan."
        )
    )
    return {
        "has_plan": has_plan,
        "planned_sessions_count": n,
        "plan_blocks_count": len(blocks),
        "sessions_per_week": sess_pw,
        "allowed_disciplines": list(discs) if isinstance(discs, list) else discs,
        "goal_text": (ath.get("goal_text") or "")[:160] or None,
        "goal_race_date": ath.get("goal_race_date"),
        "block_titles": block_titles,
        "sample_upcoming": sample,
        "intervals_connected": bool(intervals_connected),
        "icu_sync_weeks": int(icu_sync_weeks),
        "note_nb": note,
    }


def intervals_plan_sync_reply_nb(
    *,
    planned_count: int,
    icu_sync_weeks: int,
    workouts_count: int | None = None,
    intervals_connected: bool,
    from_stored: bool = True,
) -> str:
    """Honest coach reply when athlete asks to put the existing plan on Intervals."""
    if planned_count <= 0:
        return (
            "Jeg ser ingen lagret plan (planned_sessions) å synce ennå. "
            "Fullfør setup → bekreft planen først — da får vi økter til måldato i appen. "
            "Jeg finner ikke opp en ny ukeplan her."
        )
    if not intervals_connected:
        return (
            f"Planen ligger allerede her: {planned_count} økter til måldato. "
            f"Intervals er ikke koblet — gå til Du → Intervals (athlete-ID + API-nøkkel), "
            f"så synker vi nærvinduet (første {icu_sync_weeks} uker WORKOUT). "
            "Resten av planen blir i appen. Jeg lager ikke en ny plan nå."
        )
    wc = workouts_count if workouts_count is not None else "nærvinduets"
    src = "lagrede planned_sessions" if from_stored else "øktbibliotek"
    return (
        f"Planen er allerede satt ({planned_count} økter i appen). "
        f"Jeg synker ikke hele horisonten til Intervals — bare nærvinduet "
        f"({icu_sync_weeks} uker, {wc} WORKOUT fra {src}). "
        "Bekreft Sync-forhåndsvisningen. Resten av planen blir i appen."
    )


def _sport_from_text(text: str) -> str:
    raw = (text or "").lower()
    # Prefer first explicit sport token (order in text), not a fixed swim-first list.
    # Fixes «løpetur · swim» / fence sport=swim when user asked for løp.
    matches: list[tuple[int, str]] = []
    for pat, sport in (
        (r"\b(?:svøm(?:me|ming|tur)?|swim(?:ming)?)\b", "swim"),
        (r"\b(?:syk(?:kel|le|ling)?|bike|cycling)\b", "bike"),
        (r"\b(?:styrke|strength|vekt)\b", "strength"),
        (r"\b(?:løp(?:e|etur|ing)?|run(?:ning)?|jogge)\b", "run"),
        (r"\bski\b", "other"),
    ):
        m = re.search(pat, raw, re.IGNORECASE)
        if m:
            matches.append((m.start(), sport))
    if matches:
        matches.sort(key=lambda x: x[0])
        return matches[0][1]
    return "run"


def reconcile_workout_sports(
    proposal: dict[str, Any] | None,
    user_message: str = "",
) -> dict[str, Any] | None:
    """Harden sport labels: name/user beat a mismatched fence sport.

    QA: «legg inn rolig løp» sometimes returned sport=swim on the card.
    """
    if not proposal or not isinstance(proposal, dict):
        return proposal
    workouts = proposal.get("workouts")
    if not isinstance(workouts, list):
        return proposal
    user_has_sport = bool(_SPORT_WORD_RE.search(user_message or ""))
    user_sport = _sport_from_text(user_message) if user_has_sport else None
    out_ws: list[dict[str, Any]] = []
    changed = False
    for w in workouts:
        if not isinstance(w, dict):
            continue
        row = dict(w)
        sport = str(row.get("sport") or "").strip().lower()
        name = str(row.get("name") or "")
        name_has = bool(_SPORT_WORD_RE.search(name))
        name_sport = _sport_from_text(name) if name_has else None
        fixed = sport
        if name_sport and sport and name_sport != sport:
            fixed = name_sport
        elif (
            user_sport
            and sport
            and user_sport != sport
            and (not name_sport or name_sport == user_sport)
        ):
            fixed = user_sport
        if fixed != sport:
            row["sport"] = fixed
            changed = True
        out_ws.append(row)
    if not changed:
        return proposal
    return {**proposal, "workouts": out_ws}


def _relative_date_from_text(text: str, *, today: date) -> date | None:
    raw = (text or "").lower()
    if re.search(r"\bi\s+morgen\b|\btomorrow\b", raw):
        return today.fromordinal(today.toordinal() + 1)
    if re.search(r"\bi\s+dag\b|\btoday\b", raw):
        return today
    weekdays = {
        "mandag": 0,
        "tirsdag": 1,
        "onsdag": 2,
        "torsdag": 3,
        "fredag": 4,
        "lørdag": 5,
        "søndag": 6,
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    for name, target in weekdays.items():
        if re.search(rf"\b{name}\b", raw):
            delta = (target - today.weekday()) % 7
            if delta == 0:
                delta = 7
            return today.fromordinal(today.toordinal() + delta)
    return None


def infer_workout_proposal_fallback(
    user_message: str,
    reply: str,
    *,
    today: date | None = None,
) -> dict[str, Any] | None:
    """Recover a workout_proposal when the LLM forgot the fence.

    Only runs when the user clearly asked to add/change a session. Parses
    ISO dates / labeled fields from the assistant reply, then falls back to
    duration/sport/relative day in the user message.

    Duration: prefer ``duration_minutes`` in any JSON remnant, labeled varighet,
    total/totalt, sum of structure minutes, or NxM estimate — never the first
    «Oppvarming 10 min» alone (that produced «Løping 10min» stubs).
    """
    if not user_requests_session_change(user_message):
        return None
    day0 = today or date.today()
    # Prefer any workouts JSON still sitting in the reply (even without fence label).
    _disp, fenced = extract_workout_proposal(reply or "")
    if fenced and fenced.get("workouts"):
        return fenced

    date_s = None
    m_iso = _ISO_DATE_RE.search(reply or "") or _ISO_DATE_RE.search(user_message or "")
    if m_iso:
        date_s = m_iso.group(1)
    if not date_s:
        rel = _relative_date_from_text(user_message, today=day0) or _relative_date_from_text(
            reply or "", today=day0
        )
        if rel:
            date_s = rel.isoformat()
    if not date_s:
        return None

    clean_reply = strip_workout_json_from_prose(reply or "")
    blob = f"{clean_reply}\n{user_message or ''}"

    # Prefer sport from the athlete's message over assistant prose (avoids swim label on løp).
    sport = (
        (_sport_from_text(user_message) if _SPORT_WORD_RE.search(user_message or "") else None)
        or _sport_from_text(clean_reply)
        or _sport_from_text(blob)
    )
    name = None
    labeled: dict[str, str] = {}
    for lab in _LABELED_FIELD_RE.finditer(clean_reply or ""):
        chunk = lab.group(0).lower()
        val = lab.group(1).strip()
        if "økt" in chunk or "navn" in chunk:
            labeled["name"] = val
        elif "dato" in chunk:
            labeled["date"] = val
        elif "varighet" in chunk:
            labeled["duration"] = val
        elif "beskrivelse" in chunk:
            labeled["description"] = val
        elif "sport" in chunk or "disiplin" in chunk:
            labeled["sport"] = val
    if labeled.get("name"):
        name = labeled["name"][:120]
    if labeled.get("date") and _ISO_DATE_RE.search(labeled["date"]):
        date_s = _ISO_DATE_RE.search(labeled["date"]).group(1)
    if labeled.get("sport"):
        labeled_sport = _sport_from_text(labeled["sport"])
        # Don't let a wrong labeled sport override a clear user sport.
        if labeled_sport and not (
            _SPORT_WORD_RE.search(user_message or "")
            and _sport_from_text(user_message) != labeled_sport
        ):
            sport = labeled_sport or sport

    dur_i = _infer_session_duration_minutes(
        clean_reply, user_message or "", labeled.get("duration")
    )

    # Interval prescription in name (6x2) when present
    nxm = re.search(
        r"(\d+)\s*[x×]\s*(\d+)\s*(?:min(?:utt(?:er)?)?|m)?\b",
        blob,
        re.IGNORECASE,
    )
    if not name:
        if nxm:
            name = f"Intervaller {nxm.group(1)}x{nxm.group(2)}"
        else:
            sport_m = _SPORT_WORD_RE.search(user_message or "") or _SPORT_WORD_RE.search(
                clean_reply or ""
            )
            label = (sport_m.group(1) if sport_m else None) or {
                "run": "Løping",
                "bike": "Sykkel",
                "swim": "Svømming",
                "strength": "Styrke",
            }.get(sport or "", "Økt")
            # Capitalize cleanly — avoid «løping 10min» from warmup match
            name = f"{label} {dur_i} min" if dur_i else f"{label} økt"
        name = name[:120]

    # Clean structure bullets as description — never dump user_message / JSON
    description = (labeled.get("description") or "").strip()[:2000]
    if not description:
        struct_lines: list[str] = []
        for raw in (clean_reply or "").splitlines():
            line = raw.strip()
            if not line:
                continue
            if re.match(
                r"^(?:[-*•]|\d+[.)])\s+|"
                r"(?:oppvarming|hoveddel|nedkjøling|warmup|main|cooldown|"
                r"main\s*set)",
                line,
                re.IGNORECASE,
            ):
                struct_lines.append(line)
        if struct_lines:
            description = "\n".join(struct_lines[:20])[:2000]
        elif nxm:
            description = (
                f"Oppvarming 10 min\n"
                f"Hoveddel {nxm.group(1)}x{nxm.group(2)} min\n"
                f"Nedkjøling 10 min"
            )

    steps = None
    if nxm and (sport or "run") in ("run", "løp", "lop"):
        reps, mins = int(nxm.group(1)), int(nxm.group(2))
        steps = [
            {"type": "warmup", "duration_minutes": 10, "intensity": "Z2"},
        ]
        for _ in range(reps):
            steps.append({"type": "work", "duration_minutes": mins, "intensity": "Z4"})
            steps.append({"type": "recover", "duration_minutes": mins, "intensity": "Z1"})
        steps.append({"type": "cooldown", "duration_minutes": 10, "intensity": "lett"})
        if dur_i is None:
            dur_i = 10 + reps * mins * 2 + 10

    payload: dict[str, Any] = {
        "name": name,
        "date": date_s,
        "sport": sport or "run",
        "duration_minutes": dur_i,
        "description": description,
        "start_time": "07:00",
    }
    if steps:
        payload["steps"] = steps

    cleaned = _clean_workout_dicts([payload])
    if not cleaned:
        return None
    return {"workouts": cleaned, "inferred": True}


def _infer_session_duration_minutes(
    reply: str,
    user_message: str,
    labeled_duration: str | None = None,
) -> int | None:
    """Pick total session minutes — not the first warmup «10 min»."""
    if labeled_duration:
        m_lab = _DURATION_RE.search(labeled_duration)
        if m_lab:
            try:
                return int(m_lab.group(1))
            except ValueError:
                pass
    # Explicit duration_minutes in prose/JSON remnant
    m_json = re.search(
        r"duration_minutes\"?\s*[:=]\s*(\d{1,3})",
        f"{reply}\n{user_message}",
        re.IGNORECASE,
    )
    if m_json:
        try:
            return int(m_json.group(1))
        except ValueError:
            pass
    # «totalt 60 min» / «varighet 60»
    m_tot = re.search(
        r"(?:totalt|total|varighet|duration)\s*[:=]?\s*(\d{1,3})\s*(?:min|m\b)",
        f"{reply}\n{user_message}",
        re.IGNORECASE,
    )
    if m_tot:
        try:
            return int(m_tot.group(1))
        except ValueError:
            pass
    # NxM intervals → estimate warmup+main+cooldown
    nxm = re.search(
        r"(\d+)\s*[x×]\s*(\d+)\s*(?:min(?:utt(?:er)?)?|m)?\b",
        f"{reply}\n{user_message}",
        re.IGNORECASE,
    )
    if nxm:
        reps, mins = int(nxm.group(1)), int(nxm.group(2))
        return 10 + reps * mins * 2 + 10
    # Sum bullet durations if several structure lines exist
    durs: list[tuple[int, str]] = []
    for m in _DURATION_RE.finditer(reply or ""):
        try:
            val = int(m.group(1))
        except ValueError:
            continue
        # Context window around match
        start = max(0, m.start() - 24)
        ctx = (reply or "")[start : m.end() + 8].lower()
        durs.append((val, ctx))
    if not durs:
        m_u = _DURATION_RE.search(user_message or "")
        if m_u:
            try:
                return int(m_u.group(1))
            except ValueError:
                return None
        return None
    # Prefer non-warmup-only: if multiple, sum structure-like lines
    if len(durs) >= 2:
        total = sum(v for v, _ in durs)
        # Cap absurd sums; prefer largest single if sum looks like double-count
        largest = max(v for v, _ in durs)
        if total <= 180:
            return total
        return largest
    only_val, only_ctx = durs[0]
    if re.search(r"oppvarm|warmup|wu\b", only_ctx) and only_val <= 15:
        # Lone warmup mention — look at user message for total
        m_u = _DURATION_RE.search(user_message or "")
        if m_u:
            try:
                return int(m_u.group(1))
            except ValueError:
                pass
        return None  # don't invent «10min» stub name
    return only_val


def infer_plan_update_fallback(user_message: str) -> dict[str, Any] | None:
    """Recover plan_update when athlete asks to ease/rebuild and LLM skips fence."""
    if not user_requests_plan_adjust(user_message):
        return None
    text = (user_message or "").lower()
    day_swap = bool(
        re.search(
            r"(?:bytt(?:e)?|flytt(?:e)?|mov(?:e)?).{0,60}"
            r"(?:→|->|til|to)\s+"
            r"(?:man|tir|ons|tor|fre|lør|søn|monday|tuesday|wednesday|"
            r"thursday|friday|saturday|sunday)",
            text,
        )
    )
    multi_day = bool(
        re.search(
            r"helg(?:a|en)?|fre(?:dag)?|lør(?:dag)?|søn(?:dag)?|"
            r"fri(?:day)?|sat(?:urday)?|sun(?:day)?",
            text,
        )
    )
    ease = bool(re.search(r"lett|ease|letter|recover|hvile|sliten", text)) and not day_swap
    week = (
        bool(
            re.search(
                r"\buk(?:e|a|en)\b|\bweek\b|denne\s+uk(?:a|en)|neste\s+uk(?:e|a|en)|"
                r"lette?\s+uk(?:a|en)|lett\s+uke|ukeplan|plan\s+for|"
                r"erstatt(?:e)?\s+(?:hele\s+)?(?:denne\s+|neste\s+)?uk|"
                r"lette?\s+(?:neste\s+)?(?:økter|okter)",
                text,
            )
        )
        or multi_day
        or day_swap
        or ease  # «lette neste økter» / soft CTL → week card, not full rebuild
        or bool(_PLAN_WEEK_BUILD_RE.search(text))
    ) and not bool(re.search(r"hele\s+planen|full\s+plan|sesong", text))
    week_start = plan_week_target_from_message(text)
    reason = "Utleidet fra chat-forespørsel (LLM manglet plan_update-fence)."
    if day_swap:
        reason = "Ukedagsbytte foreslått — bekreft ukejustering før lagring."
    elif ease:
        reason = "Lett uke foreslått — bekreft forhåndsvisning før lagring."
    return {
        "reason": reason,
        "rebuild": True,
        "ease_load": ease,
        "scope": "week" if week else "full",
        "week_start": week_start,
        "inferred": True,
        "day_swap": day_swap,
        "message": (
            "Foreslått ukedagsbytte — bekreft forhåndsvisning."
            if day_swap
            else (
                "Foreslått ukejustering — bekreft forhåndsvisning."
                if week
                else "Foreslått planjustering — bekreft forhåndsvisning."
            )
        ),
    }


def extract_workout_removal(reply: str) -> tuple[str, dict[str, Any] | None]:
    """Strip workout_removal fence → {external_ids, dates, names}."""
    if not reply:
        return "", None
    match = _WORKOUT_REMOVAL_RE.search(reply)
    if not match:
        return reply.strip(), None
    raw = (match.group(1) or "").strip()
    display = (_WORKOUT_REMOVAL_RE.sub("", reply)).strip()
    display = _WORKOUT_PROPOSAL_RE.sub("", display)
    display = _TYPE_UPDATE_RE.sub("", display)
    display = _AGREEMENTS_UPDATE_RE.sub("", display)
    display = _PLAN_UPDATE_RE.sub("", display)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return display or reply.strip(), None
    if not isinstance(data, dict):
        return display or reply.strip(), None
    ids = [
        str(x).strip()
        for x in (data.get("external_ids") or [])
        if str(x).strip().startswith("ll-coach-")
    ]
    dates = [str(x).strip()[:10] for x in (data.get("dates") or []) if str(x).strip()]
    names = [str(x).strip()[:120] for x in (data.get("names") or []) if str(x).strip()]
    if not ids and not dates and not names:
        return display or reply.strip(), None
    return display.strip() or "Bekreft fjerning av coach-økter på Intervals.", {
        "op": "delete",
        "external_ids": ids,
        "dates": dates,
        "names": names,
    }


def extract_type_update_proposal(reply: str) -> tuple[str, dict[str, Any] | None]:
    """Strip athlete_type_update fence."""
    if not reply:
        return "", None
    match = _TYPE_UPDATE_RE.search(reply)
    if not match:
        return reply.strip(), None
    raw = (match.group(1) or "").strip()
    display = (_TYPE_UPDATE_RE.sub("", reply)).strip()
    display = _WORKOUT_PROPOSAL_RE.sub("", display)
    display = _WORKOUT_REMOVAL_RE.sub("", display)
    display = _AGREEMENTS_UPDATE_RE.sub("", display)
    display = _PLAN_UPDATE_RE.sub("", display)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return display or reply.strip(), None
    if not isinstance(data, dict):
        return display or reply.strip(), None
    from athlete_type import normalize_athlete_type, label_for

    atype = normalize_athlete_type(data.get("athlete_type"))
    if not atype:
        return display or reply.strip(), None
    return display.strip() or f"Oppdater hovedprofil til {label_for(atype)}?", {
        "op": "athlete_type_update",
        "athlete_type": atype,
        "reason": str(data.get("reason") or "").strip()[:300],
        "confirm_required": True,
        "rewrites_plan": True,
    }


def extract_agreements_update(reply: str) -> tuple[str, dict[str, Any] | None]:
    """Strip agreements_update fence → patch fields for Du-fanen (confirm before save)."""
    if not reply:
        return "", None
    match = _AGREEMENTS_UPDATE_RE.search(reply)
    if not match:
        return reply.strip(), None
    raw = (match.group(1) or "").strip()
    display = (_AGREEMENTS_UPDATE_RE.sub("", reply)).strip()
    display = _WORKOUT_PROPOSAL_RE.sub("", display)
    display = _WORKOUT_REMOVAL_RE.sub("", display)
    display = _TYPE_UPDATE_RE.sub("", display)
    display = _PLAN_UPDATE_RE.sub("", display)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return display or reply.strip(), None
    if not isinstance(data, dict):
        return display or reply.strip(), None

    from athlete_constraints import normalize_disciplines, normalize_sessions_per_week

    patch: dict[str, Any] = {"op": "agreements_update", "confirm_required": True}
    reason = str(data.get("reason") or "").strip()[:300]
    if reason:
        patch["reason"] = reason
    if data.get("goal_text"):
        patch["goal_text"] = str(data["goal_text"]).strip()[:500]
    if data.get("goal_race_date"):
        patch["goal_race_date"] = str(data["goal_race_date"]).strip()[:10]
    if data.get("fitness_notes"):
        patch["fitness_notes"] = str(data["fitness_notes"]).strip()[:500]
    if data.get("schedule_notes"):
        patch["schedule_notes"] = str(data["schedule_notes"]).strip()[:500]
    sess = normalize_sessions_per_week(data.get("sessions_per_week"))
    if sess is not None:
        patch["sessions_per_week"] = sess
    discs = normalize_disciplines(data.get("allowed_disciplines"))
    if discs:
        patch["allowed_disciplines"] = discs
    agr = data.get("agreements")
    if isinstance(agr, list):
        cleaned = [str(a).strip()[:200] for a in agr if str(a).strip()]
        if cleaned:
            patch["agreements"] = cleaned[:20]
    # Need at least one real field beyond op/confirm/reason
    if not any(
        k in patch
        for k in (
            "sessions_per_week",
            "goal_race_date",
            "goal_text",
            "allowed_disciplines",
            "agreements",
            "fitness_notes",
            "schedule_notes",
        )
    ):
        return display or reply.strip(), None
    summary_bits = []
    if "sessions_per_week" in patch:
        summary_bits.append(f"{patch['sessions_per_week']} økter/uke")
    if "goal_race_date" in patch:
        summary_bits.append(f"måldato {patch['goal_race_date']}")
    if "goal_text" in patch:
        summary_bits.append(patch["goal_text"][:80])
    patch["message"] = (
        "Oppdater treningsavtaler: " + (", ".join(summary_bits) if summary_bits else "ny avtale")
        + "?"
    )
    patch["rebuild_plan_preview"] = True
    return display.strip() or patch["message"], patch


def extract_plan_update(reply: str) -> tuple[str, dict[str, Any] | None]:
    """Strip plan_update fence → coach proposal to rebuild local plan (confirm first)."""
    if not reply:
        return "", None
    match = _PLAN_UPDATE_RE.search(reply)
    if not match:
        return reply.strip(), None
    raw = (match.group(1) or "").strip()
    display = (_PLAN_UPDATE_RE.sub("", reply)).strip()
    display = _WORKOUT_PROPOSAL_RE.sub("", display)
    display = _WORKOUT_REMOVAL_RE.sub("", display)
    display = _TYPE_UPDATE_RE.sub("", display)
    display = _AGREEMENTS_UPDATE_RE.sub("", display)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return display or reply.strip(), None
    if not isinstance(data, dict):
        return display or reply.strip(), None
    reason = str(data.get("reason") or data.get("note") or "").strip()[:400]
    rebuild = data.get("rebuild")
    if rebuild is None:
        rebuild = True
    ease = bool(data.get("ease_load") or data.get("ease"))
    scope_raw = str(data.get("scope") or "full").strip().lower()
    scope = "week" if scope_raw in ("week", "this_week", "uke") else "full"
    week_start = data.get("week_start")
    if scope == "week" and not week_start:
        week_start = "this_week"
    prop: dict[str, Any] = {
        "op": "plan_update",
        "confirm_required": True,
        "rebuild": bool(rebuild),
        "ease_load": ease,
        "scope": scope,
        "reason": reason,
        "message": reason
        or (
            "Foreslått ukejustering — forhåndsvis én uke, deretter bekreft. "
            "Resten av planen beholdes."
            if scope == "week"
            else (
                "Foreslått planjustering — forhåndsvis meso-blokker og økter til måldato, "
                "deretter bekreft. Intervals skrives først etter Sync."
            )
        ),
    }
    if scope == "week":
        prop["week_start"] = str(week_start or "this_week")[:10]
    return display.strip() or prop["message"], prop

def resolve_openai_model(model: str | None = None) -> str:
    """Normalize OPENAI_MODEL; default gpt-4o for coach smoothness."""
    raw = (model or "").strip() or "gpt-4o"
    # Common aliases / typos
    aliases = {
        "gpt4o": "gpt-4o",
        "gpt-4o-latest": "gpt-4o",
        "4o": "gpt-4o",
        "mini": "gpt-4o-mini",
        "gpt4o-mini": "gpt-4o-mini",
    }
    return aliases.get(raw.lower(), raw)


def call_llm(
    *,
    api_key: str,
    model: str,
    system: str,
    history: list[dict[str, str]],
    user_message: str,
) -> str:
    """One OpenAI chat completion. Fallback stub if no API key.

    Cursor Composer is not available via API from this app — use OPENAI_MODEL
    (default gpt-4o) for quality closer to agent-modus coaching.
    """
    if not api_key:
        return (
            f"(Utviklingsmodus — mangler OPENAI_API_KEY.) "
            f"Jeg hørte deg: «{user_message[:200]}». "
            "Koble API-nøkkel for ekte svar. Fortsett gjerne med mål, skade eller ukens fokus."
        )

    try:
        from openai import OpenAI
    except ImportError:
        return "openai-pakken mangler. pip install openai"

    use_model = resolve_openai_model(model)
    client = OpenAI(api_key=api_key)
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for m in history:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})

    # Slightly warmer + longer than mini defaults — OPV prescriptions need room.
    resp = client.chat.completions.create(
        model=use_model,
        messages=messages,
        temperature=0.7,
        max_tokens=1600,
    )
    return (resp.choices[0].message.content or "").strip()
