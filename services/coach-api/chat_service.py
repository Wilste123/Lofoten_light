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
_PLAN_UPDATE_RE = re.compile(
    r"```(?:json\s+)?plan_update\s*\n(.*?)```",
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
- Intervals-aktiviteter er fasit for *gjennomført*; app ``planned_sessions`` er fasit for *planlagt*.
  Synk nærvindu til Intervals etter bekreftelse — ikke anta at ICU er oppdatert før Sync.
- Feltet ``app_plan`` i snapshotet er sannhetskilde for lagret plan (antall økter, frekvens, disipliner, sample).
  Når ``app_plan.has_plan`` er true: du HAR laget/kjenner planen — ikke si «jeg har ikke spesifisert økttyper»
  og ikke start ny intervjuerunde om hvilke økter som skal med.
- Når utøveren ber om å legge inn / synke / pushe *planen* (eller «resten») til Intervals:
  1) Bruk eksisterende planned_sessions — ikke bygg ny ukeplan og ikke spør om økttyper.
  2) Forklar ærlig: app beholder full horisont; Intervals får kun nærvindu (icu_sync_weeks).
  3) Hvis Intervals ikke er koblet: si det rett ut + Du → Intervals — fortsatt ingen ny plan.
  4) Appen emitter Sync-forhåndsvisning (intervals_pending) — du synker ikke selv.
  5) ALDRI emit workout_proposal / plan_update / JSON-økter for sync-forespørsler.
     Prosa + fenced workouts er IKKE «det er i Intervals». Kun preview→confirm synker.
  6) ALDRI påstå at noe er synket/pushet til Intervals før utøveren har trykket Ja, sync.
- Chat og Plan-bygger deler samme modell: workout_proposal / plan_update → preview → confirm →
  lagre planned_sessions (+ plan_blocks). Ikke lag en parallell prosa-plan som ikke kan bekreftes.
- ALDRI si at økter er lagret/synket/«i Intervals» / «oppdatert» før utøveren har bekreftet kortet.
  ALDRI be dem redigere Intervals manuelt når Sync-API finnes — fail closed med ærlig feil i stedet.
- «kan du lage en økt…» / juster fre–lør/helg = WRITE: fence + kort er obligatorisk, ikke bare struktur i prosa.
- Hvis overblikk mangler ICU-data: si ærlig at *gjennomført* belastning krever Intervals-kobling;
  planlagte økter kan likevel finnes i sessions.planlagt / upcoming fra app-planen.
- «Hva har jeg denne uka?» / kommende økter: bruk sessions.planlagt / today / upcoming. Ikke finn opp økter.
- «Hva har jeg gjort?» / volum / compliance: bruk KUN sessions.gjennomfort (ICU-aktiviteter).
  NOTE og planlagt WORKOUT uten aktivitet er IKKE gjennomført trening. Si det rett ut.
- Respekter allowed_disciplines + sessions_per_week + skadenotat. Foreslå ikke svøm/sykkel/tri-uke
  når avtalen er løp+styrke. Ved brudd: nekt eller spør om å endre avtalen (agreements_update) — ikke synce stille.
- wellness_signals (søvn/HRV/RHR/load) er signaler, ikke fasit — bruk dem til *forslag*
  om å lette/flytte økter, aldri til stille omskrivning av hele planen.
{focused_bullets}- Når utøveren ber om å legge inn / endre / planlegge en konkret økt (app-plan eller Intervals):
  1) Skriv kort råd på norsk — forankret i knowledge; avvis usikre endringer.
  2) Avslutt ALLTID med ÉN fenced code block merket workout_proposal (ikke vanlig json), med:
     {{"workouts":[{{"name":"...","date":"YYYY-MM-DD","sport":"bike|run|swim|strength|other","duration_minutes":60,"description":"...","start_time":"07:00"}}]}}
  3) Uten denne fencen lagres INGENTING. Prosa alene (selv med dato/varighet) er ikke nok.
  4) Du synker IKKE selv — utøveren bekrefter i appen (forhåndsvis → lagre i plan → Sync Intervals).
  5) Bruk workout_proposal KUN når de eksplisitt ber om økt/kalenderendring; ikke for vanlig råd.
  6) Ved endring av focused_session: behold dato med mindre de ber om å flytte; oppdater description med konkrete steg.
  7) Kun sports innenfor allowed_disciplines; hold deg innenfor sessions_per_week.
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
- Når utøveren ber om å justere / bygge om grovplanen (eller etter agreements_update som krever ny periodisering):
  1) Kort råd — ta hensyn til wellness_signals hvis tilgjengelig (forslag, ikke fasit).
  2) Fenced block merket plan_update:
     {{"reason":"…","rebuild":true,"ease_load":false,"scope":"full","note":"…"}}
  3) rebuild=true + scope=full (default) → forhåndsvisning av meso + økter til måldato.
  4) Når utøveren ber om å lette / bygge om *kun denne uka*:
     {{"reason":"…","rebuild":true,"ease_load":true,"scope":"week","week_start":"this_week"}}
     → appen erstatter kun én uke i planned_sessions (resten beholdes).
  5) Utøveren bekrefter → lagre lokalt → Sync til Intervals (kun nærvindu). Ingen autonom omskrivning.
- Du kan foreslå planblokker/makro i tekst; konkrete planendringer går via plan_update (ikke bare råd).

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
    return cleaned


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
    cleaned = _clean_workout_dicts(workouts)
    if not cleaned:
        return display or reply.strip(), None
    # Strip other fences from display too
    display = _WORKOUT_REMOVAL_RE.sub("", display)
    display = _TYPE_UPDATE_RE.sub("", display)
    display = _AGREEMENTS_UPDATE_RE.sub("", display)
    display = _PLAN_UPDATE_RE.sub("", display)
    return display.strip() or (
        "Her er forslaget — bekreft i appen for å lagre i planen "
        "(deretter Sync til Intervals)."
    ), {"workouts": cleaned}


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
    r"lett(?:e)?\s+(?:denne\s+)?uka|"
    r"lette\s+uka|"
    r"ease\s+(?:the\s+)?week|"
    r"juster\s+(?:planen|uka|grovplanen|helg(?:a|en)?|fre|lør|søn)|"
    r"bygg\s+om\s+(?:planen|uka|grovplanen)|"
    r"endre\s+(?:planen|grovplanen|uka|helg(?:a|en)?|fre|lør)|"
    r"oppdater\s+(?:planen|uka|helg(?:a|en)?|fre|lør|søn)|"
    r"ny\s+(?:ukeplan|grovplan)|"
    r"rebuild\s+(?:plan|week)|"
    # Multi-day / weekend (fre–lør / helg) without requiring «planen»
    r"(?:juster|endre|oppdater|lette?)\s+"
    r"(?:fre(?:dag)?|lør(?:dag)?|søn(?:dag)?|helg(?:a|en)?)"
    r"(?:\s*(?:[-–og,&/]|til|og)\s*"
    r"(?:fre(?:dag)?|lør(?:dag)?|søn(?:dag)?|helg(?:a|en)?))?|"
    r"(?:fre|lør|søn|fredag|lørdag|søndag)\s*[-–]\s*"
    r"(?:fre|lør|søn|fredag|lørdag|søndag)"
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
_SYNC_CONFIRM_FOLLOWUP_RE = re.compile(
    r"^\s*(?:"
    r"sync|synk|go|kjør|"
    r"ja(?:\s*,?\s*(?:takk|sync|synk|gjør\s+det|push|bekreft|oppdater))?|"
    r"bekreft(?:\s+sync)?|"
    r"gjør\s+det|"
    r"push\s+det|"
    r"oppdater(?:\s+det)?|"
    r"ok(?:ay)?|"
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


def write_intent_kind(message: str) -> str | None:
    """Return 'sync' | 'session' | 'plan' | None for deterministic write routing."""
    text = (message or "").strip()
    if not text:
        return None
    if user_requests_intervals_plan_sync(text):
        return "sync"
    if user_requests_session_change(text):
        return "session"
    if user_requests_plan_adjust(text):
        return "plan"
    return None


def reopen_pending_write_reply(
    recent_messages: list[dict[str, Any]] | None,
    *,
    today: date | None = None,
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    """Rebuild proposal from last assistant turn when user says «ok»/«ja».

    Returns (reply, workout_proposal|None, plan_prop|None). Never claims success.
    """
    last = _latest_assistant_text(recent_messages)
    day0 = today or date.today()
    # Prefer extracting a real fence if the model had one in history (rare).
    _disp, fence_wp = extract_workout_proposal(last)
    if fence_wp:
        return (
            "Forslaget ligger klart — bekreft forhåndsvisningskortet. "
            "Ingenting er lagret eller synket før du trykker Ja.",
            fence_wp,
            None,
        )
    _disp, fence_pl = extract_plan_update(last)
    if fence_pl and fence_pl.get("rebuild"):
        return (
            "Planjusteringen ligger klar — bekreft forhåndsvisningen. "
            "Ingenting er lagret før du bekrefter.",
            None,
            fence_pl,
        )
    # Seed a synthetic user message so session-change gate passes.
    seed = "legg inn økt " + (last[:240] if last else "i morgen")
    inferred = infer_workout_proposal_fallback(seed, last, today=day0)
    if inferred:
        return (
            "Jeg har fortsatt forslaget klart — bekreft kortet for å lagre i planen "
            "(deretter Sync til Intervals om du vil). "
            "Jeg har ikke oppdatert noe ennå.",
            inferred,
            None,
        )
    plan_fb = infer_plan_update_fallback("juster uka")
    if last and any(
        m in last.lower()
        for m in ("uke", "helg", "fredag", "lørdag", "plan", "juster")
    ):
        return (
            "Bekreft uke-/planjustering via forhåndsvisningskortet. "
            "Jeg har ikke oppdatert Intervals eller planen ennå.",
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
    if re.search(r"\b(svøm|swim)\b", raw):
        return "swim"
    if re.search(r"\b(syk|bike|cycling)\b", raw):
        return "bike"
    if re.search(r"\b(styrke|strength)\b", raw):
        return "strength"
    if re.search(r"\b(løp|run|jogge)\b", raw):
        return "run"
    if re.search(r"\b(ski)\b", raw):
        return "other"
    return "run"


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
    """
    if not user_requests_session_change(user_message):
        return None
    day0 = today or date.today()
    blob = f"{reply or ''}\n{user_message or ''}"

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

    dur_i = None
    m_dur = _DURATION_RE.search(reply or "") or _DURATION_RE.search(user_message or "")
    if m_dur:
        try:
            dur_i = int(m_dur.group(1))
        except ValueError:
            dur_i = None

    sport = _sport_from_text(blob)
    name = None
    labeled: dict[str, str] = {}
    for lab in _LABELED_FIELD_RE.finditer(reply or ""):
        # Recover which label from the match span
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
    if labeled.get("duration") and dur_i is None:
        m_lab_dur = _DURATION_RE.search(labeled["duration"])
        if m_lab_dur:
            try:
                dur_i = int(m_lab_dur.group(1))
            except ValueError:
                pass
    if labeled.get("sport"):
        sport = _sport_from_text(labeled["sport"]) or sport
    if not name:
        sport_m = _SPORT_WORD_RE.search(user_message or "") or _SPORT_WORD_RE.search(
            reply or ""
        )
        label = sport_m.group(1) if sport_m else sport
        name = f"{label} {dur_i}min" if dur_i else f"{label} økt"
        name = name[:120]

    description = (labeled.get("description") or "").strip()[:2000]
    if not description:
        description = (user_message or "").strip()[:500]

    cleaned = _clean_workout_dicts(
        [
            {
                "name": name,
                "date": date_s,
                "sport": sport,
                "duration_minutes": dur_i,
                "description": description,
                "start_time": "07:00",
            }
        ]
    )
    if not cleaned:
        return None
    return {"workouts": cleaned, "inferred": True}


def infer_plan_update_fallback(user_message: str) -> dict[str, Any] | None:
    """Recover plan_update when athlete asks to ease/rebuild and LLM skips fence."""
    if not user_requests_plan_adjust(user_message):
        return None
    text = (user_message or "").lower()
    multi_day = bool(
        re.search(
            r"helg(?:a|en)?|fre(?:dag)?|lør(?:dag)?|søn(?:dag)?|"
            r"fri(?:day)?|sat(?:urday)?|sun(?:day)?",
            text,
        )
    )
    week = (
        bool(re.search(r"\buke\b|\bweek\b|denne\s+uka|lette?\s+uka", text))
        or multi_day
    ) and not bool(re.search(r"hele\s+planen|full\s+plan|sesong", text))
    ease = bool(re.search(r"lett|ease|letter|recover|hvile", text))
    return {
        "reason": "Utleidet fra chat-forespørsel (LLM manglet plan_update-fence).",
        "rebuild": True,
        "ease_load": ease,
        "scope": "week" if week else "full",
        "week_start": "this_week",
        "inferred": True,
        "message": (
            "Foreslått ukejustering — bekreft forhåndsvisning."
            if week
            else "Foreslått planjustering — bekreft forhåndsvisning."
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
