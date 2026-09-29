"""Single-LLM-call chat — no intent router, no tool loop.

Main Coach-tab chat (`POST /v1/chat`), session-detail chat (same endpoint +
`session_id`), and setup chat share the same honest coach voice via
``HONEST_COACH_VOICE`` (imported by setup_plan).
"""

from __future__ import annotations

import json
import re
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
HONEST_COACH_VOICE = """
Stemme (all chat — ikke tippy):
- Selvsikker, ærlig, anbefalingsorientert. Én klar anbefaling per svar; ikke «det kommer an på» uten konklusjon.
- Struktur: fakta (fra snapshot/profil/knowledge) → observasjon → anbefaling. Skill planlagt fra gjennomført.
- Når mål + erfaring/form/volum/økter-per-uke ikke henger sammen ifølge Knowledge: si det rett ut
  («dette er ikke realistisk slik det står nå»), begrunn kort, deretter 2–4 konkrete alternativer
  (flere økter, senere racedato, annet/enklere mål, eller fasert rebuild). Hardkod ikke enkelt-scenario —
  generaliser fra knowledge (maalrealisme, feil-og-fixes §9, load-and-intensity, lav-frekvens).
- Be om manglende nøkkelinfo når du trenger det (1–2 spørsmål om gangen): erfaring, nåværende form/volum,
  tilgjengelige økter/uke, mål-event + dato + målsetning, skader, begrensninger.
- Når utøveren godtar et alternativ: bekreft avtalen eksplisitt og bruk extract/proposal-feltene så den persisteres
  (sessions_per_week, goal_race_date, agreements, osv.).
- Ingen Pondus / tool-loop. Én LLM-respons. Ingen tom motivasjon.
- Wellness (søvn/HRV/RHR/CTL): signaler, ikke absolutt sannhet — vei inn, ikke styr hele planen etter ett tall.
""".strip()

# Optional structured proposal the UI can preview→confirm onto Intervals.
_WORKOUT_PROPOSAL_RE = re.compile(
    r"```(?:json\s+)?workout_proposal\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
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


def build_system_prompt(
    athlete: dict[str, Any],
    knowledge_dir,
    overview_stub: dict[str, Any] | None = None,
    athletes_dir: Path | None = None,
    *,
    query_text: str = "",
    focused_session: dict[str, Any] | None = None,
    user_message: str = "",
) -> str:
    """Single coach system prompt for main chat and Økter detail chat.

    Session focus only extends knowledge retrieval + a few regler bullets —
    no separate prompt builder. Honest voice via HONEST_COACH_VOICE.
    """
    personality = athlete.get("coach_personality") or "direkte"
    hint = PERSONALITY_HINTS.get(personality, PERSONALITY_HINTS["direkte"])
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
    if focused:
        focused_bullets = (
            "- focused_session finnes i snapshotet: utøveren er i økt-detaljvisning. "
            "Svar konkret om DEN økten (beskrivelse/steg/struktur). Ikke bytt tema uten at de ber om det. Samme ærlige stemme.\n"
            "- Bruk knowledge for sporten/økttypen (intervaller, soner, Plan B). "
            "Ved workout_proposal: konkrete Warmup / Main / Cooldown-steg; behold dato med mindre de ber om å flytte.\n"
            "- Hvis de ber om hardere/lengre økt som bryter knowledge eller skaderegler: si nei, kort hvorfor, bedre alternativ.\n"
        )
    else:
        focused_bullets = (
            "- Hvis feltet focused_session finnes i snapshotet: utøveren er i økt-detaljvisning. "
            "Svar konkret om DEN økten (beskrivelse/steg). Ikke bytt tema uten at de ber om det.\n"
        )

    return f"""Du er {coach}, personlig utholdenhetstrener for {name}.
Språk: norsk. Tone: {hint}
{HONEST_COACH_VOICE}
Stil-notat fra utøveren: {athlete.get("coach_style_note") or "(ingen)"}
Nåværende hovedprofil / utøvertype: {atype}
Avtalt frekvens: {sess_line}
Avtaler: {agr_line}
(Typen og avtaler er muterbare — etter ærlig forhandling, foreslå oppdatering og la utøveren bekrefte.)

Regler:
- Én klar anbefaling; ikke generisk motivasjonsprat.
- Svar med fakta → observasjon → anbefaling når du vurderer belastning/uke.
- Vurder målrealisme (erfaring × form × økter/uke × tid til race × tidmål) før du lover race/PB — se knowledge maalrealisme; foreslå alternativ ved urealistisk mål.
- Pushback når forespørsel er urealistisk (2019-volum, for hard kvalitet, manglende Plan B, skadesignaler): si nei og gi smartere alternativ.
- Ros kontinuitet og smarte valg — ikke hero-TSS.
- Ikke still medisinsk diagnose. Ved smerte/GI: tilpass råd og anbefal fagperson ved behov.
- Ikke anta Williams historikk med mindre det står i profilen.
- Ikke anta Lofoten Half Extreme / triatlon 2027 / 750t med mindre utøveren (eller seeded william-profil) har det som mål.
- Ernæring/IBS: les GI-feltene i profilen; bruk knowledge/ernaring; aldri diagnostiser.
- Intervals eier øktdetaljer; du eier mål/avtaler/skade/ernæring/form-kontekst.
- Hvis overblikk mangler ICU-data: si ærlig at belastning krever Intervals-kobling.
- «Hva har jeg denne uka?» / kommende økter: bruk sessions.planlagt / today / upcoming. Ikke finn opp økter.
- «Hva har jeg gjort?» / volum / compliance: bruk KUN sessions.gjennomfort (ICU-aktiviteter).
  NOTE og planlagt WORKOUT uten aktivitet er IKKE gjennomført trening. Si det rett ut.
- Respekter allowed_disciplines + sessions_per_week + skadenotat. Foreslå ikke svøm/sykkel/tri-uke
  når avtalen er løp+styrke. Ved brudd: nekt eller spør om å endre avtalen (agreements_update) — ikke synce stille.
- wellness_signals (søvn/HRV/RHR/load) er signaler, ikke fasit.
{focused_bullets}- Når utøveren ber om å legge inn / endre en konkret økt på Intervals-kalenderen:
  1) Skriv kort råd på norsk — forankret i knowledge; avvis usikre endringer.
  2) Avslutt med ÉN fenced code block merket workout_proposal (ikke vanlig json), med:
     {{"workouts":[{{"name":"...","date":"YYYY-MM-DD","sport":"bike|run|swim|strength|other","duration_minutes":60,"description":"...","start_time":"07:00"}}]}}
  3) Du synker IKKE selv — utøveren bekrefter i appen (forhåndsvis → sync).
  4) Bruk workout_proposal KUN når de eksplisitt ber om kalenderøkt / endring; ikke for vanlig råd.
  5) Ved endring av focused_session: behold dato med mindre de ber om å flytte; oppdater description med konkrete steg.
  6) Kun sports innenfor allowed_disciplines; hold deg innenfor sessions_per_week.
- Når utøveren ber om å FJERNE coach-planlagte økter fra Intervals:
  1) Kort råd.
  2) Fenced block merket workout_removal:
     {{"external_ids":["ll-coach-w-…"],"dates":["YYYY-MM-DD"],"names":["…"]}}
  3) Kun coach-ids (ll-coach- / ll-coach-w-). Ingen stille sletting.
- Når mål/fokus tydelig skifter (f.eks. generell → halvmaraton-løper):
  1) Forklar kort.
  2) Fenced block merket athlete_type_update:
     {{"athlete_type":"half_marathon_runner","reason":"…"}}
  3) Utøveren må bekrefte før typen lagres og plan følger ny type.
- Når ærlig forhandling endrer avtaler (økter/uke, måldato, måltekst, disipliner):
  1) Oppsummer avtalen klart.
  2) Fenced block merket agreements_update:
     {{"sessions_per_week":4,"goal_race_date":"YYYY-MM-DD","goal_text":"…","allowed_disciplines":["run","strength"],"agreements":["4 økter/uke","…"],"reason":"…"}}
  3) Kun felt som faktisk er avtalt; null/utelat resten. Utøveren bekrefter før lagring.
- Du kan foreslå planblokker/makro i tekst; grovplan-noter synces under Plan-fanen (ikke via workout_proposal).

## Profil
{profile_md}

## Overblikk-snapshot (JSON)
{overview_json}

## Knowledge (trimmet, adaptiv)
{knowledge}
"""


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


def extract_workout_proposal(reply: str) -> tuple[str, dict[str, Any] | None]:
    """Strip optional workout_proposal fence; return (display_text, proposal|None)."""
    if not reply:
        return "", None
    match = _WORKOUT_PROPOSAL_RE.search(reply)
    if not match:
        return reply.strip(), None
    raw = (match.group(1) or "").strip()
    display = (_WORKOUT_PROPOSAL_RE.sub("", reply)).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return reply.strip(), None
    if not isinstance(data, dict):
        return reply.strip(), None
    workouts = data.get("workouts")
    if not isinstance(workouts, list) or not workouts:
        return display or reply.strip(), None
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
        cleaned.append(
            {
                "name": name[:120],
                "date": date_s,
                "sport": sport,
                "duration_minutes": dur_i,
                "description": str(w.get("description") or "").strip()[:2000],
                "start_time": start[:5],
            }
        )
    if not cleaned:
        return display or reply.strip(), None
    # Strip other fences from display too
    display = _WORKOUT_REMOVAL_RE.sub("", display)
    display = _TYPE_UPDATE_RE.sub("", display)
    display = _AGREEMENTS_UPDATE_RE.sub("", display)
    return display.strip() or "Her er forslaget — bekreft i appen før det synces til Intervals.", {
        "workouts": cleaned
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
    return display.strip() or patch["message"], patch


def call_llm(
    *,
    api_key: str,
    model: str,
    system: str,
    history: list[dict[str, str]],
    user_message: str,
) -> str:
    """One OpenAI chat completion. Fallback stub if no API key."""
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

    client = OpenAI(api_key=api_key)
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for m in history:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.6,
        max_tokens=900,
    )
    return (resp.choices[0].message.content or "").strip()
