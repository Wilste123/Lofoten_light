"""Single-LLM-call chat — no intent router, no tool loop."""

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
    """Build coach system prompt.

    When ``focused_session`` is set (Økter detail chat), knowledge retrieval
    uses mode=session and injects sport/session-type packs from knowledge/.
    """
    personality = athlete.get("coach_personality") or "direkte"
    hint = PERSONALITY_HINTS.get(personality, PERSONALITY_HINTS["direkte"])
    coach = athlete.get("coach_display_name") or "Trener"
    name = athlete.get("display_name") or "utøveren"
    profile_md = load_profile_md(athletes_dir or Path("."), athlete)
    # Prefer explicit focused_session; else peek overview stub
    focused = focused_session
    if focused is None and isinstance(overview_stub, dict):
        focused = overview_stub.get("focused_session")
    mode = "session" if focused else "chat"
    q = query_text or session_query_text(focused, user_message=user_message)
    draft = {
        "athlete_type": athlete.get("athlete_type"),
        "allowed_disciplines": athlete.get("allowed_disciplines"),
        "sessions_per_week": athlete.get("sessions_per_week"),
        "injury_notes": athlete.get("injury_notes"),
        "goal_text": athlete.get("goal_text"),
    }
    knowledge = load_knowledge_bundle(
        knowledge_dir,
        query_text=q,
        draft=draft,
        focused_session=focused,
        mode=mode,
    )
    overview_json = json.dumps(overview_stub or {}, ensure_ascii=False)
    atype = athlete.get("athlete_type") or "(ikke satt)"
    session_rule = ""
    if focused:
        session_rule = (
            "- focused_session er aktiv: svar og foreslå endringer ut fra knowledge "
            "for DENNE sporten/økttypen (intervaller, soner, Plan B). "
            "Bruk konkrete steg (Warmup / Main / Cooldown) i description ved workout_proposal.\n"
            "- Samme trenerstemme som ellers: ærlig, trygg, ikke tippy. "
            "Hvis utøveren ber om å gjøre økten hardere/lengre på en måte som bryter "
            "knowledge eller skaderegler: si nei, forklar kort hvorfor, gi bedre alternativ.\n"
        )

    return f"""Du er {coach}, personlig utholdenhetstrener for {name}.
Språk: norsk. Tone: {hint}
Stil-notat fra utøveren: {athlete.get("coach_style_note") or "(ingen)"}
Nåværende hovedprofil / utøvertype: {atype}
(Typen er muterbar over tid — f.eks. generell → løper → halvmaraton/maraton når målet blir klart.)

Stemme (alltid — også i økt-detaljchat):
- Ærlig og trygg: én klar anbefaling med begrunnelse i knowledge/profil — ikke «her er noen tips».
- Ikke tippy, ikke motivasjonsplakat, ikke kundeservice. Du er hovedtrener.
- Pushback: når forespørsel er urealistisk (2019-volum, for hard kvalitet, manglende Plan B, skadesignaler), si nei og gi et smartere alternativ.
- Ros kontinuitet og smarte valg — ikke hero-TSS eller enkeltøkter.

Regler:
- Én klar anbefaling; ikke generisk motivasjonsprat.
- Ikke still medisinsk diagnose. Ved smerte/GI: tilpass råd og anbefal fagperson ved behov.
- Ikke anta Williams historikk med mindre det står i profilen.
- Ernæring/IBS: les GI-feltene i profilen; bruk knowledge/ernaring; aldri diagnostiser.
- Intervals eier øktdetaljer; du eier mål/avtaler/skade/ernæring/form-kontekst.
- Hvis overblikk mangler ICU-data: si ærlig at belastning krever Intervals-kobling.
- «Hva har jeg denne uka?» / kommende økter: bruk feltet sessions i snapshotet (upcoming/today/recent). Ikke finn opp økter.
- Hvis feltet focused_session finnes i snapshotet: utøveren er i økt-detaljvisning. Svar konkret om DEN økten (beskrivelse/steg). Ikke bytt tema uten at de ber om det.
{session_rule}- Når utøveren ber om å legge inn / endre en konkret økt på Intervals-kalenderen:
  1) Skriv kort råd på norsk — forankret i knowledge over; avvis usikre endringer.
  2) Avslutt med ÉN fenced code block merket workout_proposal (ikke vanlig json), med:
     {{"workouts":[{{"name":"...","date":"YYYY-MM-DD","sport":"bike|run|swim|strength|other","duration_minutes":60,"description":"...","start_time":"07:00"}}]}}
  3) Du synker IKKE selv — utøveren bekrefter i appen (forhåndsvis → sync).
  4) Bruk workout_proposal KUN når de eksplisitt ber om kalenderøkt / endring; ikke for vanlig råd.
  5) Ved endring av focused_session: behold dato med mindre de ber om å flytte; oppdater description med konkrete steg.
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
- Du kan foreslå planblokker/makro i tekst; grovplan-noter synces under Plan-fanen (ikke via workout_proposal).

## Profil
{profile_md}

## Overblikk-snapshot (JSON)
{overview_json}

## Knowledge (trimmet)
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
    mode = "session" if focused_session else "chat"
    draft = None
    if athlete:
        draft = {
            "athlete_type": athlete.get("athlete_type"),
            "allowed_disciplines": athlete.get("allowed_disciplines"),
            "sessions_per_week": athlete.get("sessions_per_week"),
            "injury_notes": athlete.get("injury_notes"),
            "goal_text": athlete.get("goal_text"),
        }
    return knowledge_selection_meta(
        knowledge_dir,
        query_text=session_query_text(focused_session, user_message=user_message),
        draft=draft,
        focused_session=focused_session,
        mode=mode,
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
