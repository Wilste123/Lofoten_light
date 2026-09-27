"""Persist and resolve training agreements: disciplines + sessions/week.

Grounds plan sync / setup preview so half-marathon / run+strength athletes
never inherit the default triathlon daily pack. Thin heuristics over setup
text + athlete_type — no Pondus loop.
"""

from __future__ import annotations

import json
import re
from typing import Any

from athlete_type import (
    TYPE_BEGINNER_MULTI,
    TYPE_CYCLIST,
    TYPE_GENERAL,
    TYPE_HALF_MARATHON,
    TYPE_MARATHON,
    TYPE_RUNNER,
    TYPE_SWIMMER,
    TYPE_TRIATHLETE,
    normalize_athlete_type,
)

# Canonical ids stored on athletes.allowed_disciplines (JSON list)
DISC_RUN = "run"
DISC_BIKE = "bike"
DISC_SWIM = "swim"
DISC_STRENGTH = "strength"

VALID_DISCIPLINES = frozenset({DISC_RUN, DISC_BIKE, DISC_SWIM, DISC_STRENGTH})

# ICU / CSV sport string → canonical
SPORT_TO_DISC: dict[str, str] = {
    "run": DISC_RUN,
    "running": DISC_RUN,
    "løp": DISC_RUN,
    "lop": DISC_RUN,
    "bike": DISC_BIKE,
    "ride": DISC_BIKE,
    "cycling": DISC_BIKE,
    "sykkel": DISC_BIKE,
    "swim": DISC_SWIM,
    "swimming": DISC_SWIM,
    "svøm": DISC_SWIM,
    "svom": DISC_SWIM,
    "strength": DISC_STRENGTH,
    "weighttraining": DISC_STRENGTH,
    "styrke": DISC_STRENGTH,
}

DISC_TO_SPORT: dict[str, str] = {
    DISC_RUN: "Run",
    DISC_BIKE: "Bike",
    DISC_SWIM: "Swim",
    DISC_STRENGTH: "Strength",
}

LABELS_NO: dict[str, str] = {
    DISC_RUN: "løp",
    DISC_BIKE: "sykkel",
    DISC_SWIM: "svøm",
    DISC_STRENGTH: "styrke",
}

# Sensible default sessions/week when not stated (None = no hard cap / use template)
DEFAULT_SESSIONS: dict[str, int | None] = {
    TYPE_HALF_MARATHON: 4,
    TYPE_MARATHON: 4,
    TYPE_RUNNER: 4,
    TYPE_CYCLIST: 5,
    TYPE_SWIMMER: 5,
    TYPE_TRIATHLETE: None,  # use full ukemaler week (william / explicit tri)
    TYPE_BEGINNER_MULTI: 5,
    TYPE_GENERAL: 3,  # commercial get-in-shape — never uncapped tri week
}

# Empty list = no discipline filter (legacy multi / william tri default)
# Commercial general → run+strength until athlete names sports
DEFAULT_DISCIPLINES: dict[str, list[str]] = {
    TYPE_HALF_MARATHON: [DISC_RUN, DISC_STRENGTH],
    TYPE_MARATHON: [DISC_RUN, DISC_STRENGTH],
    TYPE_RUNNER: [DISC_RUN, DISC_STRENGTH],
    TYPE_CYCLIST: [DISC_BIKE, DISC_STRENGTH, DISC_RUN],
    TYPE_SWIMMER: [DISC_SWIM, DISC_STRENGTH, DISC_RUN],
    TYPE_TRIATHLETE: [],  # all
    TYPE_BEGINNER_MULTI: [],
    TYPE_GENERAL: [DISC_RUN, DISC_STRENGTH],
}

MIN_SESSIONS = 2
MAX_SESSIONS = 8
MAX_WORKOUT_WEEKS = 2


def sport_to_discipline(sport: str | None) -> str | None:
    if not sport:
        return None
    key = str(sport).strip().lower().replace(" ", "")
    return SPORT_TO_DISC.get(key)


def normalize_disciplines(raw: Any) -> list[str] | None:
    """Parse list / CSV / JSON into canonical ordered unique disciplines."""
    if raw is None or raw == "":
        return None
    items: list[Any]
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                items = parsed if isinstance(parsed, list) else [s]
            except json.JSONDecodeError:
                items = re.split(r"[,/;+|]+", s)
        else:
            items = re.split(r"[,/;+|]+", s)
    elif isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        return None
    out: list[str] = []
    for it in items:
        d = sport_to_discipline(str(it))
        if d and d in VALID_DISCIPLINES and d not in out:
            out.append(d)
    return out or None


def disciplines_to_storage(disciplines: list[str] | None) -> str:
    discs = normalize_disciplines(disciplines) or []
    return json.dumps(discs, ensure_ascii=False)


def disciplines_from_storage(raw: Any) -> list[str]:
    return normalize_disciplines(raw) or []


def normalize_sessions_per_week(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        n = int(float(raw))
    except (TypeError, ValueError):
        return None
    if MIN_SESSIONS <= n <= MAX_SESSIONS:
        return n
    return None


def _blob(draft: dict[str, Any] | None, extra: str = "") -> str:
    draft = draft or {}
    parts = [extra]
    for k in (
        "goal_text",
        "schedule_notes",
        "background_notes",
        "notes",
        "coach_respect_notes",
        "injury_notes",
        "agreements",
        "allowed_disciplines",
    ):
        v = draft.get(k)
        if isinstance(v, list):
            parts.append(" ".join(str(x) for x in v))
        else:
            parts.append(str(v or ""))
    return " ".join(parts).lower()


def infer_sessions_per_week(
    draft: dict[str, Any] | None = None,
    *,
    athlete_type: str | None = None,
    text: str = "",
) -> int | None:
    """Explicit field → regex in schedule → type default (None = no hard cap)."""
    draft = draft or {}
    explicit = normalize_sessions_per_week(draft.get("sessions_per_week"))
    if explicit is not None:
        return explicit

    blob = _blob(draft, text)
    patterns = (
        r"(\d)\s*(?:økter|okter|sessions?|ganger)\s*(?:/|per|i)?\s*uke",
        r"(\d)\s*(?:×|x)\s*(?:uke|week)",
        r"kun\s+(\d)\s*(?:økter|okter|sessions?)",
        r"bare\s+(\d)\s*(?:økter|okter|sessions?)",
        r"(\d)\s*økter\s*i\s*uka",
    )
    for pat in patterns:
        m = re.search(pat, blob)
        if m:
            n = normalize_sessions_per_week(m.group(1))
            if n is not None:
                return n

    atype = normalize_athlete_type(athlete_type or draft.get("athlete_type")) or TYPE_GENERAL
    return DEFAULT_SESSIONS.get(atype)


def infer_allowed_disciplines(
    draft: dict[str, Any] | None = None,
    *,
    athlete_type: str | None = None,
    text: str = "",
) -> list[str]:
    """Explicit list → conversation cues → athlete_type default."""
    draft = draft or {}
    explicit = normalize_disciplines(draft.get("allowed_disciplines"))
    if explicit:
        return explicit

    blob = _blob(draft, text)
    atype = normalize_athlete_type(athlete_type or draft.get("athlete_type")) or TYPE_GENERAL

    # Strong "only X" agreements beat type defaults
    only_run_strength = bool(
        re.search(
            r"(kun|bare|only)\s+(løp|lop|running|run).{0,40}(styrke|strength)"
            r"|(løp|lop|run).{0,20}(og|&|\+)\s*(styrke|strength).{0,30}"
            r"(ikke|uten|no)\s*(svøm|svom|sykkel|swim|bike|tri)",
            blob,
        )
        or re.search(
            r"(ikke|uten|no)\s+(svøm|svom|sykkel|swim|bike|tri).{0,40}"
            r"(kun|bare|only).{0,20}(løp|lop|run|styrke)",
            blob,
        )
        or re.search(
            r"(kun|bare)\s+(løping|løpe|running).{0,30}(styrke|strength)",
            blob,
        )
    )
    if only_run_strength or (
        atype in (TYPE_HALF_MARATHON, TYPE_MARATHON, TYPE_RUNNER)
        and re.search(r"halv\s*maraton|half[\s-]?marathon|maraton|løper", blob)
        and not re.search(r"triatlon|triathlon|svøm|sykkel|lofoten", blob)
    ):
        # Runners default to run+strength unless they ask for more
        if re.search(r"\bsykkel\b|\bbike\b", blob) and not only_run_strength:
            return [DISC_RUN, DISC_BIKE, DISC_STRENGTH]
        return [DISC_RUN, DISC_STRENGTH]

    only_bike = bool(
        re.search(r"(kun|bare|only)\s+(sykkel|bike|cycling)", blob)
        and not re.search(r"triatlon|triathlon", blob)
    )
    if only_bike:
        discs = [DISC_BIKE, DISC_STRENGTH]
        if re.search(r"\bløp\b|\brun\b", blob):
            discs.append(DISC_RUN)
        return discs

    return list(DEFAULT_DISCIPLINES.get(atype, DEFAULT_DISCIPLINES[TYPE_GENERAL]))


def resolve_constraints(
    athlete: dict[str, Any] | None = None,
    draft: dict[str, Any] | None = None,
    *,
    athlete_type: str | None = None,
    text: str = "",
) -> dict[str, Any]:
    """Merge persisted athlete fields with draft/inference for plan sync."""
    athlete = athlete or {}
    draft = draft or {}
    atype = normalize_athlete_type(
        athlete_type
        or draft.get("athlete_type")
        or athlete.get("athlete_type")
    ) or TYPE_GENERAL

    merged = {
        **draft,
        "athlete_type": atype,
        "goal_text": draft.get("goal_text") or athlete.get("goal_text") or "",
        "schedule_notes": draft.get("schedule_notes")
        or athlete.get("schedule_notes")
        or "",
        "notes": draft.get("notes") or athlete.get("notes") or "",
        "injury_notes": draft.get("injury_notes")
        or athlete.get("injury_notes")
        or "",
        "background_notes": draft.get("background_notes") or "",
        "agreements": draft.get("agreements") or athlete.get("agreements") or [],
    }
    if draft.get("allowed_disciplines") not in (None, "", []):
        merged["allowed_disciplines"] = draft["allowed_disciplines"]
    elif athlete.get("allowed_disciplines") not in (None, "", []):
        merged["allowed_disciplines"] = athlete["allowed_disciplines"]
    if draft.get("sessions_per_week") not in (None, ""):
        merged["sessions_per_week"] = draft["sessions_per_week"]
    elif athlete.get("sessions_per_week") not in (None, ""):
        merged["sessions_per_week"] = athlete["sessions_per_week"]

    disciplines = infer_allowed_disciplines(
        merged, athlete_type=atype, text=text
    )
    sessions = infer_sessions_per_week(merged, athlete_type=atype, text=text)

    return {
        "athlete_type": atype,
        "allowed_disciplines": disciplines,
        "sessions_per_week": sessions,
        "disciplines_labels_no": [LABELS_NO[d] for d in disciplines],
        "max_workout_weeks": MAX_WORKOUT_WEEKS,
    }


def split_for_disciplines(
    athlete_type: str | None,
    disciplines: list[str] | None,
    *,
    base_split: dict[str, float] | None = None,
) -> dict[str, float]:
    """Zero disallowed sports and renormalize to 1.0."""
    from athlete_type import SPLITS, TYPE_GENERAL as TG

    tid = athlete_type if athlete_type in SPLITS else TG
    split = dict(base_split or SPLITS.get(tid, SPLITS[TG]))
    discs = set(normalize_disciplines(disciplines) or [])
    if not discs:
        return split
    key_map = {
        "swim": DISC_SWIM,
        "bike": DISC_BIKE,
        "run": DISC_RUN,
        "strength": DISC_STRENGTH,
    }
    for k, d in key_map.items():
        if d not in discs:
            split[k] = 0.0
    total = sum(split.values())
    if total <= 0:
        # Fallback: equal across allowed
        n = len(discs)
        return {
            "swim": (1.0 / n) if DISC_SWIM in discs else 0.0,
            "bike": (1.0 / n) if DISC_BIKE in discs else 0.0,
            "run": (1.0 / n) if DISC_RUN in discs else 0.0,
            "strength": (1.0 / n) if DISC_STRENGTH in discs else 0.0,
        }
    return {k: round(v / total, 4) for k, v in split.items()}


def constraints_summary_nb(constraints: dict[str, Any]) -> str:
    labels = constraints.get("disciplines_labels_no") or []
    n = constraints.get("sessions_per_week")
    disc = " + ".join(labels) if labels else "alle disipliner (etter type)"
    n_bit = f"{n} økter/uke" if n else "ukemaler-økter"
    return f"{n_bit} · {disc} · max {constraints.get('max_workout_weeks', 2)} uker WORKOUT"
