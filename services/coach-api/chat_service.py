"""Single-LLM-call chat — no intent router, no tool loop."""

from __future__ import annotations

import json
import re
from typing import Any

from pathlib import Path

from knowledge_ctx import load_knowledge_bundle
from profile import load_profile_md


PERSONALITY_HINTS = {
    "direkte": "Direkte, konkret, lite fluff — som en erfaren utholdenhetstrener.",
    "støttende": "Støttende men ærlig; ros steady progress, utfordre urealistisk volum.",
    "teknisk": "Teknisk og presis; soner, TSS, struktur — uten å overforklare.",
    "opv": "Ole Petter Vibekken-inspirert: struktur, krav, ærlig risiko — tilpasset tri/comeback.",
}

# Optional structured proposal the UI can preview→confirm onto Intervals.
_WORKOUT_PROPOSAL_RE = re.compile(
    r"```(?:json\s+)?workout_proposal\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def build_system_prompt(
    athlete: dict[str, Any],
    knowledge_dir,
    overview_stub: dict[str, Any] | None = None,
    athletes_dir: Path | None = None,
) -> str:
    personality = athlete.get("coach_personality") or "direkte"
    hint = PERSONALITY_HINTS.get(personality, PERSONALITY_HINTS["direkte"])
    coach = athlete.get("coach_display_name") or "Trener"
    name = athlete.get("display_name") or "utøveren"
    profile_md = load_profile_md(athletes_dir or Path("."), athlete)
    knowledge = load_knowledge_bundle(knowledge_dir)
    overview_json = json.dumps(overview_stub or {}, ensure_ascii=False)

    return f"""Du er {coach}, personlig utholdenhetstrener for {name}.
Språk: norsk. Tone: {hint}
Stil-notat fra utøveren: {athlete.get("coach_style_note") or "(ingen)"}

Regler:
- Én klar anbefaling; ikke generisk motivasjonsprat.
- Ikke still medisinsk diagnose. Ved smerte/GI: tilpass råd og anbefal fagperson ved behov.
- Ikke anta Williams historikk med mindre det står i profilen.
- Ernæring/IBS: les GI-feltene i profilen; bruk knowledge/ernaring; aldri diagnostiser.
- Intervals eier øktdetaljer; du eier mål/avtaler/skade/ernæring/form-kontekst.
- Hvis overblikk mangler ICU-data: si ærlig at belastning krever Intervals-kobling.
- «Hva har jeg denne uka?» / kommende økter: bruk feltet sessions i snapshotet (upcoming/today/recent). Ikke finn opp økter.
- Når utøveren ber om å legge inn / endre en konkret økt på Intervals-kalenderen:
  1) Skriv kort råd på norsk.
  2) Avslutt med ÉN fenced code block merket workout_proposal (ikke vanlig json), med:
     {{"workouts":[{{"name":"...","date":"YYYY-MM-DD","sport":"bike|run|swim|strength|other","duration_minutes":60,"description":"...","start_time":"07:00"}}]}}
  3) Du synker IKKE selv — utøveren bekrefter i appen (forhåndsvis → sync).
  4) Bruk workout_proposal KUN når de eksplisitt ber om kalenderøkt; ikke for vanlig råd.
- Du kan foreslå planblokker/makro i tekst; grovplan-noter synces under Plan-fanen (ikke via workout_proposal).

## Profil
{profile_md}

## Overblikk-snapshot (JSON)
{overview_json}

## Knowledge (trimmet)
{knowledge}
"""


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
    return display or "Her er forslaget — bekreft i appen før det synces til Intervals.", {
        "workouts": cleaned
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
