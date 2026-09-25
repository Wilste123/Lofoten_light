"""Single-LLM-call chat — no intent router, no tool loop."""

from __future__ import annotations

import json
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

## Profil
{profile_md}

## Overblikk-snapshot (JSON)
{overview_json}

## Knowledge (trimmet)
{knowledge}
"""


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
