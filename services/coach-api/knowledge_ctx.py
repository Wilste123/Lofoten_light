"""Load trimmed knowledge snippets — adaptive by athlete signals / chat text.

Thin retrieval: keyword heuristics pick files from knowledge/. No vector DB / Pondus.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Always-on coaching identity + decision rules
CORE_COACH = [
    "coach/coach-filosofi.md",
    "coach/treneridentitet.md",
    "coach/ole-grenser.md",
    "coach/feil-og-fixes.md",
]

# Periodization / load science — always for plan generation
CORE_PLAN = [
    "triathlon/periodisering-mot-2027.md",
    "coach/ukemaler.md",
    "load-and-intensity.md",
]

# Run / HM / low-frequency — injected when athlete is not multi-sport default
CORE_RUN_PLAN = [
    "lop/ukeplaner-lav-frekvens.md",
    "lop/styrke-og-lop.md",
    "load-and-intensity.md",
]

CORE_HM_PLAN = [
    "lop/halvmaraton-periodisering.md",
    "lop/ukeplaner-lav-frekvens.md",
    "lop/styrke-og-lop.md",
]

CORE_GENERAL_PLAN = [
    "coach/ukeplaner-generell-utholdenhet.md",
    "lop/ukeplaner-lav-frekvens.md",
    "load-and-intensity.md",
]

ERNARING_CORE = [
    "ernaring/coach-chat-kort.md",
    "ernaring/ibs-og-gluten.md",
]

# Sport packs for session-detail chat (always inject when focused økt matches)
SESSION_SPORT_PACKS: dict[str, list[str]] = {
    "bike": [
        "sykkel/intervaller-og-sonearbeid.md",
        "sykkel/kraft-og-utholdenhet.md",
        "sykkel/ror-sykkel-og-terreng.md",
        "coach/opv-nokkelokter.md",
        "coach/intervals-tekst-opv.md",
    ],
    "run": [
        "lop/intervaller-og-fart.md",
        "lop/terreng-og-fjell.md",
        "lop/oppbygging-etter-pause.md",
        "lop/styrke-og-lop.md",
        "coach/opv-nokkelokter.md",
    ],
    "swim": [
        "svom/trening-og-periodisering.md",
        "svom/nybegynner-til-triatlet.md",
        "svom/apent-vann-kulde.md",
    ],
    "strength": [
        "skader/forebygging-styrke-mobilitet.md",
        "lop/styrke-og-lop.md",
    ],
    "other": [
        "load-and-intensity.md",
        "coach/ukemaler.md",
    ],
}

# Session-type cues → extra files (elghufs, brick, open water, …)
SESSION_TYPE_PACKS: list[tuple[list[str], list[str]]] = [
    (
        ["elghufs", "myr", "staver", "trail", "terreng", "fjell"],
        ["coach/opv-nokkelokter.md", "lop/terreng-og-fjell.md"],
    ),
    (
        ["brick", "overgang", "kombinert"],
        ["triathlon/brick-og-overgang.md"],
    ),
    (
        ["ows", "åpent vann", "apent vann", "kulde", "våtdrakt"],
        ["svom/apent-vann-kulde.md"],
    ),
    (
        ["z4", "terskel", "threshold", "vo2", "intervaller", "crisscross", "18×3", "18x3"],
        ["sykkel/intervaller-og-sonearbeid.md", "lop/intervaller-og-fart.md", "coach/opv-nokkelokter.md"],
    ),
    (
        ["styrke", "strength", "core", "mobilitet"],
        ["skader/forebygging-styrke-mobilitet.md", "lop/styrke-og-lop.md"],
    ),
]

# Conditional packs (path → trigger keywords, Norwegian + English stems)
CONDITIONAL_PACKS: list[tuple[list[str], list[str]]] = [
    (
        [
            "nybegynner",
            "begynn",
            "aldri trent",
            "aldri trena",
            "helt ny",
            "første gang",
            "første tri",
            "beginner",
            "newbie",
            "null erfaring",
            "ingen erfaring",
            "kan ikke svømme",
            "lære å svømme",
        ],
        [
            "svom/nybegynner-til-triatlet.md",
            "mental/kontinuitet-motivasjon.md",
            "utstyr/triatlon-grunnpakke.md",
        ],
    ),
    (
        [
            "comeback",
            "etter pause",
            "lang pause",
            "returning",
            "eks-atlet",
            "eks syklist",
            "tidligere elite",
            "har trent før",
            "tilbake etter",
            "rebuild",
            "ikke trent på",
            "2019",
            "gammel form",
        ],
        [
            "lop/oppbygging-etter-pause.md",
            "coach/ole-petter-vibekken-referanse.md",
            "sykkel/kraft-og-utholdenhet.md",
        ],
    ),
    (
        [
            "skade",
            "isjas",
            "rygg",
            "kne",
            "achilles",
            "akilles",
            "skulder",
            "smerte",
            "injury",
            "rehab",
            "comeback etter skade",
            "plager",
            "belastning",
            "acwr",
        ],
        [
            "skader/belastningsstyring-acwr.md",
            "skader/oversikt-utholdenhet.md",
            "skader/forebygging-styrke-mobilitet.md",
            "skader/lop-skadeprofiler.md",
        ],
    ),
    (
        [
            "tidsklemma",
            "lite tid",
            "full jobb",
            "familie",
            "barn",
            "time-constrained",
            "busy",
            "kun ",
            "timer i uka",
            "t/uke",
            "få timer",
        ],
        [
            "coach/ukemaler.md",
            "mental/kontinuitet-motivasjon.md",
            "restitusjon/sovn-stress.md",
        ],
    ),
    (
        [
            "svøm",
            "svom",
            "swim",
            "basseng",
            "ows",
            "åpent vann",
            "apent vann",
        ],
        [
            "svom/nybegynner-til-triatlet.md",
            "svom/trening-og-periodisering.md",
            "svom/apent-vann-kulde.md",
        ],
    ),
    (
        [
            "løp",
            "lop",
            "run",
            "maraton",
            "terreng",
            "trail",
        ],
        [
            "lop/oppbygging-etter-pause.md",
            "lop/intervaller-og-fart.md",
            "lop/terreng-og-fjell.md",
            "lop/ukeplaner-lav-frekvens.md",
            "lop/styrke-og-lop.md",
        ],
    ),
    (
        [
            "halvmaraton",
            "halv maraton",
            "half marathon",
            "half-marathon",
            "21 km",
            "21k",
            "hm ",
        ],
        [
            "lop/halvmaraton-periodisering.md",
            "lop/ukeplaner-lav-frekvens.md",
            "lop/styrke-og-lop.md",
            "lop/intervaller-og-fart.md",
        ],
    ),
    (
        [
            "3 økter",
            "3 okter",
            "tre økter",
            "2 økter",
            "4 økter",
            "få økter",
            "kun løp",
            "bare løp",
            "løp og styrke",
            "lop og styrke",
            "run and strength",
            "sessions per week",
            "økter/uke",
            "okter/uke",
        ],
        [
            "lop/ukeplaner-lav-frekvens.md",
            "lop/styrke-og-lop.md",
            "coach/ukeplaner-generell-utholdenhet.md",
            "restitusjon/sovn-stress.md",
        ],
    ),
    (
        [
            "nybegynner løp",
            "starte å løpe",
            "lære å løpe",
            "første 5 km",
            "begynne å jogge",
        ],
        [
            "lop/nybegynner-lop.md",
            "lop/ukeplaner-lav-frekvens.md",
            "skader/lop-skadeprofiler.md",
        ],
    ),
    (
        [
            "sykkel",
            "bike",
            "ftp",
            "watt",
            "rulle",
        ],
        [
            "sykkel/kraft-og-utholdenhet.md",
            "sykkel/intervaller-og-sonearbeid.md",
            "sykkel/ror-sykkel-og-terreng.md",
        ],
    ),
    (
        [
            "lofoten",
            "half extreme",
            "norseman",
            "extreme",
            "ironman",
            "half",
            "triatlon",
            "triathlon",
            "brick",
        ],
        [
            "triathlon/lofoten-half-extreme.md",
            "triathlon/brick-og-overgang.md",
            "triathlon/periodisering-mot-2027.md",
        ],
    ),
    (
        [
            "ibs",
            "gluten",
            "laktose",
            "mage",
            "ernæring",
            "ernaring",
            "mat",
            "fueling",
        ],
        [
            "ernaring/coach-chat-kort.md",
            "ernaring/ibs-og-gluten.md",
            "ernaring/grunnlag.md",
        ],
    ),
]


def _read_trimmed(path: Path, max_chars: int) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n\n[…trimmet…]"


def _norm(text: str) -> str:
    return (text or "").lower()


def detect_athlete_signals(text: str, draft: dict[str, Any] | None = None) -> dict[str, bool]:
    """Heuristic flags used for knowledge selection + plan divergence docs."""
    blob = _norm(text)
    if draft:
        for k in (
            "goal_text",
            "injury_notes",
            "schedule_notes",
            "background_notes",
            "notes",
            "coach_respect_notes",
            "fitness_notes",
        ):
            blob += " " + _norm(str(draft.get(k) or ""))
    fitness_ok = bool(
        re.search(
            r"form\s+(er\s+)?(ok|grei|bra|fin|god)|allerede\s+i\s+form|trener\s+allerede|"
            r"fitness\s+ok|holder\s+formen|ikke\s+comeback|form ok|ikke re-etablering",
            blob,
        )
    )
    # Require real comeback / pause cues — not bare «tidligere» or «var i form»
    returning = bool(
        re.search(
            r"comeback|etter\s+pause|lang\s+pause|returning|eks-atlet|eks\s+syklist|"
            r"har\s+trent\s+før|tilbake\s+etter|rebuild|oppbygging\s+etter\s+pause|"
            r"ikke\s+trent\s+på",
            blob,
        )
    )
    if fitness_ok:
        returning = False
    return {
        "beginner": bool(
            re.search(
                r"nybegynner|aldri trent|helt ny|ingen erfaring|beginner|kan ikke svømme",
                blob,
            )
        )
        and not fitness_ok,
        "returning": returning,
        "fitness_ok": fitness_ok,
        "injury": bool(
            re.search(r"skade|isjas|rygg|kne|achilles|smerte|rehab|plager", blob)
        ),
        "time_constrained": bool(
            re.search(r"lite tid|tidsklemma|full jobb|familie|få timer|busy", blob)
        ),
        # Require real multi-sport / race cues — bare «løp»/«svøm» alone is NOT triathlon.
        "multisport": bool(
            re.search(
                r"triatlon|triathlon|lofoten|half\s*extreme|ironman|halviron|"
                r"norseman|brick|flersport|alle tre|svøm.*sykkel.*løp|"
                r"swim.*bike.*run",
                blob,
            )
        ),
    }


def _athlete_type_plan_paths(draft: dict[str, Any] | None, blob: str) -> list[str]:
    """Prefer run/HM/general packs over tri CORE_PLAN when type/cues say so."""
    draft = draft or {}
    atype = _norm(str(draft.get("athlete_type") or ""))
    discs = _norm(str(draft.get("allowed_disciplines") or ""))
    run_primary = (
        "runner" in atype
        or atype == "runner"
        or "half_marathon" in atype
        or "marathon" in atype
    )
    multi = bool(
        re.search(r"triatlon|triathlon|lofoten|half\s*extreme|ironman", blob)
    ) or atype in ("triathlete", "beginner_multi")
    low_freq = bool(
        re.search(
            r"3 økter|3 okter|tre økter|2 økter|4 økter|kun løp|løp og styrke|"
            r"sessions_per_week.: ?[234]",
            blob + " " + discs,
        )
    ) or (
        str(draft.get("sessions_per_week") or "") in ("2", "3", "4")
    )

    if multi and not run_primary:
        return list(CORE_PLAN)

    out: list[str] = []
    if "half_marathon" in atype or re.search(r"halv\s*maraton|half[\s-]?marathon", blob):
        out.extend(CORE_HM_PLAN)
    elif run_primary or re.search(r"\bløper\b|\bløping\b|running", blob):
        out.extend(CORE_RUN_PLAN)
        if re.search(r"nybegynner|aldri trent|starte å løpe", blob):
            out.append("lop/nybegynner-lop.md")
        out.append("lop/oppbygging-etter-pause.md")
    elif atype in ("general_endurance", "general", "") or not multi:
        out.extend(CORE_GENERAL_PLAN)
    else:
        out.extend(CORE_PLAN)

    if low_freq:
        for p in (
            "lop/ukeplaner-lav-frekvens.md",
            "lop/styrke-og-lop.md",
            "coach/ukeplaner-generell-utholdenhet.md",
        ):
            if p not in out:
                out.append(p)

    # Always keep load science
    if "load-and-intensity.md" not in out:
        out.append("load-and-intensity.md")
    # Tri periodization only when multi
    if multi and "triathlon/periodisering-mot-2027.md" not in out:
        out.insert(0, "triathlon/periodisering-mot-2027.md")
        if "coach/ukemaler.md" not in out:
            out.insert(1, "coach/ukemaler.md")
    return out


def _discipline_key(raw: str | None) -> str:
    d = _norm(raw or "")
    if d in ("bike", "sykkel", "cycling", "ride"):
        return "bike"
    if d in ("run", "løp", "lop", "running", "trail"):
        return "run"
    if d in ("swim", "svøm", "svom", "swimming"):
        return "swim"
    if d in ("strength", "styrke", "weight", "gym"):
        return "strength"
    return "other"


def session_query_text(
    session: dict[str, Any] | None,
    *,
    user_message: str = "",
) -> str:
    """Build retrieval blob from focused økt + athlete message."""
    if not session:
        return user_message or ""
    bits = [
        user_message or "",
        str(session.get("name") or ""),
        str(session.get("discipline") or ""),
        str(session.get("discipline_label") or ""),
        str(session.get("type") or ""),
        str(session.get("category") or ""),
        str(session.get("description") or "")[:1200],
    ]
    for step in session.get("steps") or []:
        bits.append(str(step))
    return " ".join(bits)


def select_knowledge_paths(
    *,
    mode: str = "chat",
    query_text: str = "",
    draft: dict[str, Any] | None = None,
    focused_session: dict[str, Any] | None = None,
    max_conditional: int = 10,
) -> list[str]:
    """Ordered unique relative paths under knowledge/."""
    paths: list[str] = []
    paths.extend(CORE_COACH)

    blob = _norm(query_text)
    if focused_session:
        blob += " " + _norm(session_query_text(focused_session))
    if draft:
        for k in (
            "goal_text",
            "injury_notes",
            "schedule_notes",
            "background_notes",
            "notes",
            "coach_respect_notes",
            "athlete_type",
            "allowed_disciplines",
            "sessions_per_week",
        ):
            blob += " " + _norm(str(draft.get(k) or ""))

    if mode == "plan":
        paths.extend(_athlete_type_plan_paths(draft, blob))
    elif mode in ("setup", "chat"):
        # Lighter core + type-aware hints
        paths.extend(_athlete_type_plan_paths(draft, blob)[:4])
        paths.append("load-and-intensity.md")
        # Same chat retrieval — extended when focused økt is in context
        if focused_session:
            disc = _discipline_key(
                focused_session.get("discipline")
                or focused_session.get("sport")
                or ""
            )
            for p in SESSION_SPORT_PACKS.get(disc, SESSION_SPORT_PACKS["other"]):
                if p not in paths:
                    paths.append(p)
            for triggers, files in SESSION_TYPE_PACKS:
                if any(t in blob for t in triggers):
                    for f in files:
                        if f not in paths:
                            paths.append(f)

    paths.extend(ERNARING_CORE)

    conditional: list[str] = []
    for triggers, files in CONDITIONAL_PACKS:
        if any(t in blob for t in triggers):
            for f in files:
                if f not in paths and f not in conditional:
                    conditional.append(f)
    cap = max_conditional + (4 if focused_session else 0)
    paths.extend(conditional[:cap])

    # Deduplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def load_knowledge_bundle(
    knowledge_dir: Path,
    *,
    coach_budget: int = 3500,
    ernaring_budget: int = 2500,
    query_text: str = "",
    draft: dict[str, Any] | None = None,
    focused_session: dict[str, Any] | None = None,
    mode: str = "chat",
    total_budget: int | None = None,
) -> str:
    """Backward-compatible loader; when query/draft/session given, uses adaptive selection."""
    adaptive = bool(query_text or draft or focused_session)
    if not adaptive:
        # Legacy chat path
        parts: list[str] = []
        per_coach = coach_budget // max(len(CORE_COACH), 1)
        for rel in CORE_COACH:
            chunk = _read_trimmed(knowledge_dir / rel, per_coach)
            if chunk:
                parts.append(f"### {rel}\n{chunk}")
        per_ern = ernaring_budget // max(len(ERNARING_CORE), 1)
        for rel in ERNARING_CORE:
            chunk = _read_trimmed(knowledge_dir / rel, per_ern)
            if chunk:
                parts.append(f"### {rel}\n{chunk}")
        return "\n\n".join(parts)

    budget = total_budget or (9000 if mode == "plan" else 6500)
    if focused_session and mode == "chat":
        budget = total_budget or 7500
    paths = select_knowledge_paths(
        mode=mode,
        query_text=query_text,
        draft=draft,
        focused_session=focused_session,
    )
    if not paths:
        return ""
    per = max(400, budget // len(paths))
    parts = []
    used: list[str] = []
    for rel in paths:
        chunk = _read_trimmed(knowledge_dir / rel, per)
        if chunk:
            parts.append(f"### {rel}\n{chunk}")
            used.append(rel)
    header = f"(knowledge paths: {', '.join(used)})\n\n" if used else ""
    return header + "\n\n".join(parts)


def knowledge_selection_meta(
    knowledge_dir: Path,
    *,
    query_text: str = "",
    draft: dict[str, Any] | None = None,
    focused_session: dict[str, Any] | None = None,
    mode: str = "plan",
) -> dict[str, Any]:
    paths = select_knowledge_paths(
        mode=mode,
        query_text=query_text,
        draft=draft,
        focused_session=focused_session,
    )
    existing = [p for p in paths if (knowledge_dir / p).is_file()]
    disc = None
    if focused_session:
        disc = _discipline_key(
            focused_session.get("discipline") or focused_session.get("sport")
        )
    return {
        "signals": detect_athlete_signals(query_text, draft),
        "paths": existing,
        "mode": mode,
        "discipline": disc,
    }
