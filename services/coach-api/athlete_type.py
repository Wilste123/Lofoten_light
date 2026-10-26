"""Infer and persist primary athlete type / hoveddisiplin from onboarding.

Half-marathon runners must not inherit the default triathlon swim/bike/run pack.
"""

from __future__ import annotations

import re
from typing import Any

# Stable ids stored on athletes.athlete_type
TYPE_HALF_MARATHON = "half_marathon_runner"
TYPE_MARATHON = "marathon_runner"
TYPE_RUNNER = "runner"
TYPE_CYCLIST = "cyclist"
TYPE_SWIMMER = "swimmer"
TYPE_TRIATHLETE = "triathlete"
TYPE_BEGINNER_MULTI = "beginner_multi"
TYPE_GENERAL = "general_endurance"

LABELS_NO: dict[str, str] = {
    TYPE_HALF_MARATHON: "halvmaraton-løper",
    TYPE_MARATHON: "maraton-løper",
    TYPE_RUNNER: "løper",
    TYPE_CYCLIST: "syklist",
    TYPE_SWIMMER: "svømmer",
    TYPE_TRIATHLETE: "triatlet",
    TYPE_BEGINNER_MULTI: "nybegynner flersport",
    TYPE_GENERAL: "generell utholdenhet",
}

# Maps to athletes.sport (existing column) when we persist
SPORT_FOR_TYPE: dict[str, str] = {
    TYPE_HALF_MARATHON: "running",
    TYPE_MARATHON: "running",
    TYPE_RUNNER: "running",
    TYPE_CYCLIST: "cycling",
    TYPE_SWIMMER: "swimming",
    TYPE_TRIATHLETE: "triathlon",
    TYPE_BEGINNER_MULTI: "triathlon",
    TYPE_GENERAL: "endurance",
}

# Season hour splits (swim, bike, run, strength) — must sum to 1.0
SPLITS: dict[str, dict[str, float]] = {
    TYPE_HALF_MARATHON: {"swim": 0.0, "bike": 0.08, "run": 0.80, "strength": 0.12},
    TYPE_MARATHON: {"swim": 0.0, "bike": 0.08, "run": 0.80, "strength": 0.12},
    TYPE_RUNNER: {"swim": 0.0, "bike": 0.10, "run": 0.78, "strength": 0.12},
    TYPE_CYCLIST: {"swim": 0.0, "bike": 0.82, "run": 0.06, "strength": 0.12},
    TYPE_SWIMMER: {"swim": 0.72, "bike": 0.08, "run": 0.08, "strength": 0.12},
    TYPE_TRIATHLETE: {"swim": 0.16, "bike": 0.50, "run": 0.30, "strength": 0.04},
    TYPE_BEGINNER_MULTI: {"swim": 0.20, "bike": 0.35, "run": 0.35, "strength": 0.10},
    TYPE_GENERAL: {"swim": 0.05, "bike": 0.35, "run": 0.45, "strength": 0.15},
}

VALID_TYPES = frozenset(LABELS_NO)


def _norm(text: str) -> str:
    return (text or "").lower()


def draft_blob(draft: dict[str, Any] | None, extra: str = "") -> str:
    draft = draft or {}
    parts = [extra]
    for k in (
        "goal_text",
        "injury_notes",
        "schedule_notes",
        "background_notes",
        "notes",
        "coach_respect_notes",
        "sport",
        "athlete_type",
        "weekly_focus",
    ):
        parts.append(str(draft.get(k) or ""))
    return _norm(" ".join(parts))


def infer_athlete_type(
    text: str = "",
    draft: dict[str, Any] | None = None,
    *,
    signals: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Heuristic primary discipline from conversation + draft + optional signals."""
    draft = draft or {}
    explicit = str(draft.get("athlete_type") or "").strip().lower().replace(" ", "_")
    blob = draft_blob(draft, text)
    signals = signals or {}

    # Draft triathlete must not win over clear run/HM goals without multisport cues.
    # QA: setup LLM set triathlete despite «halvmaraton + løp/styrke, svømming vanskelig».
    draft_tri_override = False
    if explicit in (TYPE_TRIATHLETE, TYPE_BEGINNER_MULTI):
        hm_or_run = bool(
            re.search(
                r"halv\s*maraton|half[\s-]?marathon|\b21\s*km\b|\b21k\b|"
                r"\bmaraton\b|marathon|\bløper\b|\bløping\b|\brunner\b",
                blob,
            )
        )
        real_multi = bool(
            re.search(
                r"triatlon|triathlon|half\s*extreme|lofoten|ironman|halviron|"
                r"norseman|brick|flersport|alle tre",
                blob,
            )
        ) or bool(signals.get("multisport"))
        if hm_or_run and not real_multi:
            draft_tri_override = True
        else:
            return _pack(explicit, source="draft")
    elif explicit in VALID_TYPES:
        return _pack(explicit, source="draft")

    swim_difficulty = bool(
        re.search(
            r"(?:svøm|swim).{0,40}(?:vanskelig|kan ikke|dårlig|sliter|hate)|"
            r"kan ikke svømme|ikke svøm(?:me|ming)?|"
            r"(?:uten|no)\s+(?:svøm|swim)",
            blob,
        )
    )

    # Explicit race / discipline cues (order matters — more specific first)
    if re.search(
        r"halv\s*maraton|half[\s-]?marathon|\b21\s*km\b|\b21k\b|hm\b",
        blob,
    ):
        return _pack(
            TYPE_HALF_MARATHON,
            source="goal_half_marathon_over_draft_tri"
            if draft_tri_override
            else "goal_half_marathon",
        )
    if re.search(r"\bmaraton\b|marathon|\b42\s*km\b|\b42k\b", blob) and not re.search(
        r"halv|half", blob
    ):
        return _pack(TYPE_MARATHON, source="goal_marathon")
    if re.search(
        r"triatlon|triathlon|half\s*extreme|lofoten|ironman|halviron|norseman|brick",
        blob,
    ):
        if signals.get("beginner") or re.search(r"nybegynner|aldri trent", blob):
            return _pack(TYPE_BEGINNER_MULTI, source="tri_beginner")
        return _pack(TYPE_TRIATHLETE, source="multisport")
    if re.search(
        r"\bsyklist\b|\bsykkel\b|cycling|ftp|zwift|wattbasert|tempo på sykkel",
        blob,
    ) and not re.search(r"triatlon|triathlon|lofoten", blob):
        return _pack(TYPE_CYCLIST, source="bike_focus")
    if (
        re.search(
            r"\bsvømmer\b|open water|basseng.*fokus|swim focus|"
            r"(?:hovedidrett|fokus).{0,20}(?:svøm|swim)",
            blob,
        )
        and not swim_difficulty
        and not re.search(r"triatlon|triathlon|lofoten|halv\s*maraton|løp\s+og\s+styrke", blob)
    ):
        return _pack(TYPE_SWIMMER, source="swim_focus")
    if re.search(
        r"\bløper\b|\bløping\b|\brunner\b|running|jogge|5\s*km|10\s*km|trail.?løp|"
        r"løp\s+og\s+styrke|løp-fokus|run.?focus",
        blob,
    ) and not re.search(r"triatlon|triathlon|lofoten|sykkel.*og.*løp", blob):
        return _pack(TYPE_RUNNER, source="run_focus")

    sport = _norm(str(draft.get("sport") or ""))
    if sport in ("running", "run", "løp", "lop"):
        return _pack(TYPE_RUNNER, source="sport_field")
    if sport in ("cycling", "bike", "sykkel"):
        return _pack(TYPE_CYCLIST, source="sport_field")
    if sport in ("swimming", "swim", "svøm", "svom"):
        return _pack(TYPE_SWIMMER, source="sport_field")
    if sport in ("triathlon", "tri", "triatlon"):
        if signals.get("beginner"):
            return _pack(TYPE_BEGINNER_MULTI, source="sport_beginner")
        return _pack(TYPE_TRIATHLETE, source="sport_field")

    if signals.get("beginner") and signals.get("multisport"):
        return _pack(TYPE_BEGINNER_MULTI, source="signals")
    if signals.get("multisport"):
        return _pack(TYPE_TRIATHLETE, source="signals")
    if signals.get("beginner"):
        return _pack(TYPE_GENERAL, source="beginner_general")

    return _pack(TYPE_GENERAL, source="default")


def _pack(type_id: str, *, source: str) -> dict[str, Any]:
    return {
        "athlete_type": type_id,
        "label_no": LABELS_NO.get(type_id, type_id),
        "sport": SPORT_FOR_TYPE.get(type_id, "endurance"),
        "split": dict(SPLITS.get(type_id, SPLITS[TYPE_GENERAL])),
        "source": source,
        "is_run_primary": type_id
        in (TYPE_HALF_MARATHON, TYPE_MARATHON, TYPE_RUNNER),
        "is_bike_primary": type_id == TYPE_CYCLIST,
        "is_swim_primary": type_id == TYPE_SWIMMER,
        "is_multisport": type_id in (TYPE_TRIATHLETE, TYPE_BEGINNER_MULTI),
    }


def normalize_athlete_type(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    t = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "half_marathon": TYPE_HALF_MARATHON,
        "halvmaraton": TYPE_HALF_MARATHON,
        "halvmaraton_loper": TYPE_HALF_MARATHON,
        "marathon": TYPE_MARATHON,
        "run": TYPE_RUNNER,
        "lop": TYPE_RUNNER,
        "loper": TYPE_RUNNER,
        "bike": TYPE_CYCLIST,
        "cycling": TYPE_CYCLIST,
        "sykkel": TYPE_CYCLIST,
        "swim": TYPE_SWIMMER,
        "svom": TYPE_SWIMMER,
        "tri": TYPE_TRIATHLETE,
        "triathlon": TYPE_TRIATHLETE,
        "triatlon": TYPE_TRIATHLETE,
        "beginner": TYPE_BEGINNER_MULTI,
        "general": TYPE_GENERAL,
        "generell": TYPE_GENERAL,
    }
    t = aliases.get(t, t)
    return t if t in VALID_TYPES else None


def label_for(type_id: str | None) -> str:
    if not type_id:
        return LABELS_NO[TYPE_GENERAL]
    return LABELS_NO.get(type_id, type_id)


def split_for(type_id: str | None) -> dict[str, float]:
    tid = type_id if type_id in VALID_TYPES else TYPE_GENERAL
    return dict(SPLITS[tid])


def append_type_history(
    existing_notes: str | None,
    *,
    old_type: str | None,
    new_type: str,
    reason: str = "",
    at_iso: str | None = None,
) -> str:
    """Append a short line when type changes (mutable over the season)."""
    from datetime import datetime, timezone

    at = at_iso or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    old_l = label_for(old_type) if old_type else "—"
    new_l = label_for(new_type)
    line = f"{at}: {old_l} → {new_l}"
    if reason:
        line += f" ({reason.strip()[:160]})"
    prev = (existing_notes or "").strip()
    if not prev:
        return line
    # Avoid duplicate consecutive identical transitions
    if prev.splitlines()[-1].startswith(f"{at}: {old_l} → {new_l}"):
        return prev
    return prev + "\n" + line


def propose_type_update(
    athlete: dict[str, Any],
    *,
    suggested: str | None = None,
    text: str = "",
    draft: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """If evidence points to a new type, return a proposal (no silent write).

    Thin: caller shows preview → athlete confirms before persist / plan rewrite.
    """
    current = normalize_athlete_type(athlete.get("athlete_type")) or TYPE_GENERAL
    if suggested:
        new = normalize_athlete_type(suggested)
    else:
        info = infer_athlete_type(
            text,
            {
                **(draft or {}),
                "goal_text": (draft or {}).get("goal_text")
                or athlete.get("goal_text")
                or "",
                "notes": (draft or {}).get("notes") or athlete.get("notes") or "",
                "sport": (draft or {}).get("sport") or athlete.get("sport") or "",
            },
        )
        new = info["athlete_type"]
    if not new or new == current:
        return None
    return {
        "op": "athlete_type_update",
        "from": current,
        "to": new,
        "from_label": label_for(current),
        "to_label": label_for(new),
        "sport": SPORT_FOR_TYPE.get(new, "endurance"),
        "confirm_required": True,
        "rewrites_plan": True,
        "message": (
            f"Oppdater hovedprofil fra «{label_for(current)}» til «{label_for(new)}»? "
            "Bekreft før plan/økter følger den nye typen."
        ),
    }
