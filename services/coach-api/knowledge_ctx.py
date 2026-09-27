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

ERNARING_CORE = [
    "ernaring/coach-chat-kort.md",
    "ernaring/ibs-og-gluten.md",
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
            "pause",
            "tidligere",
            "før i tiden",
            "returning",
            "eks-",
            "eks ",
            "tidligere elite",
            "tidligere syklist",
            "tidligere løper",
            "har trent før",
            "var i form",
            "2019",
            "gammel form",
            "rebuild",
            "tilbake etter",
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
        ):
            blob += " " + _norm(str(draft.get(k) or ""))
    return {
        "beginner": bool(
            re.search(
                r"nybegynner|aldri trent|helt ny|ingen erfaring|beginner|kan ikke svømme",
                blob,
            )
        ),
        "returning": bool(
            re.search(
                r"comeback|pause|tidligere|returning|eks-|har trent før|var i form|rebuild",
                blob,
            )
        ),
        "injury": bool(
            re.search(r"skade|isjas|rygg|kne|achilles|smerte|rehab|plager", blob)
        ),
        "time_constrained": bool(
            re.search(r"lite tid|tidsklemma|full jobb|familie|få timer|busy", blob)
        ),
        "multisport": bool(
            re.search(r"triatlon|triathlon|lofoten|svøm|sykkel|løp|brick", blob)
        ),
    }


def select_knowledge_paths(
    *,
    mode: str = "chat",
    query_text: str = "",
    draft: dict[str, Any] | None = None,
    max_conditional: int = 8,
) -> list[str]:
    """Ordered unique relative paths under knowledge/."""
    paths: list[str] = []
    paths.extend(CORE_COACH)
    if mode in ("plan", "setup", "chat"):
        paths.extend(CORE_PLAN if mode == "plan" else CORE_PLAN[:2])
    paths.extend(ERNARING_CORE)

    blob = _norm(query_text)
    if draft:
        for k in (
            "goal_text",
            "injury_notes",
            "schedule_notes",
            "background_notes",
            "notes",
            "coach_respect_notes",
        ):
            blob += " " + _norm(str(draft.get(k) or ""))

    conditional: list[str] = []
    for triggers, files in CONDITIONAL_PACKS:
        if any(t in blob for t in triggers):
            for f in files:
                if f not in paths and f not in conditional:
                    conditional.append(f)
    paths.extend(conditional[:max_conditional])

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
    mode: str = "chat",
    total_budget: int | None = None,
) -> str:
    """Backward-compatible loader; when query/draft given, uses adaptive selection."""
    if not query_text and not draft:
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
    paths = select_knowledge_paths(mode=mode, query_text=query_text, draft=draft)
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
    mode: str = "plan",
) -> dict[str, Any]:
    paths = select_knowledge_paths(mode=mode, query_text=query_text, draft=draft)
    existing = [p for p in paths if (knowledge_dir / p).is_file()]
    return {
        "signals": detect_athlete_signals(query_text, draft),
        "paths": existing,
        "mode": mode,
    }
