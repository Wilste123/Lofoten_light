"""Personalize library workout coach text for the active athlete.

``workouts/planned/**`` files are William-seeded templates. At preview/push time
we rewrite greetings to the athlete's display name and strip William-only
injury/context (isjas, finger, …) unless that athlete's profile mentions them.
"""

from __future__ import annotations

import re
from typing import Any

# Addressee forms in library copy: "William, …" / "William — …"
_WILLIAM_ADDR_RE = re.compile(r"\bWilliam(\s*[,—–\-]\s*)", re.IGNORECASE)
_WILLIAM_WORD_RE = re.compile(r"\bWilliam\b", re.IGNORECASE)

# William-seed injury topics — keep only when athlete profile matches.
_ISJAS_RE = re.compile(
    r"isjas|isjasnerven|nerve[- ]?trekk|nerven bråker|rygg og isjas|rygg/isjas|"
    r"glidning isjas|følte rygg/isjas|prikking|sciatic",
    re.IGNORECASE,
)
_FINGER_RE = re.compile(
    r"kuttskade|skadet finger|finger og infeksjon|trykk på skadet finger|"
    r"ingen basseng denne uken|fortsatt \*\*ingen svøm\*\*|erstatter svøm",
    re.IGNORECASE,
)
_3T_WILLIAM_RE = re.compile(
    r"ingen 3[Tt] denne dagen|på 3[Tt], ikke hjemme|ta med drikke og sko",
    re.IGNORECASE,
)

# Title fragments that assume William's rygg/isjas prehab.
_TITLE_ISJAS_RE = re.compile(
    r"\s*[—(]\s*rygg/?isjas[^)]*\)?|\s+rygg/isjas\b|\s*—\s*rygg,\s*isjas[^\n]*",
    re.IGNORECASE,
)


def athlete_display_name(athlete: dict[str, Any] | None) -> str:
    athlete = athlete or {}
    name = (athlete.get("display_name") or "").strip()
    return name or "du"


def athlete_context_blob(athlete: dict[str, Any] | None) -> str:
    athlete = athlete or {}
    parts = [
        athlete.get("injury_notes") or "",
        athlete.get("notes") or "",
        athlete.get("schedule_notes") or "",
        athlete.get("goal_text") or "",
        athlete.get("athlete_type") or "",
    ]
    return " ".join(str(p) for p in parts if p).lower()


def athlete_injury_flags(athlete: dict[str, Any] | None) -> dict[str, bool]:
    """Which William-library injury topics apply to this athlete."""
    blob = athlete_context_blob(athlete)
    rygg_isjas = bool(
        re.search(r"isjas|sciatic|ryggplag|rygg\b|lumbago|prolaps|nervesmerte", blob)
    )
    finger = bool(re.search(r"finger|kuttskade|sår på hånd|infeksjon.*finger", blob))
    has_injury_notes = bool(str((athlete or {}).get("injury_notes") or "").strip())
    return {
        "rygg_isjas": rygg_isjas,
        "finger": finger,
        "any_injury": has_injury_notes or rygg_isjas or finger,
    }


def replace_william_addressee(text: str, display_name: str) -> str:
    """Swap library 'William' greetings for the active athlete's name."""
    if not text:
        return text
    name = (display_name or "du").strip() or "du"
    # Preserve punctuation after the name ("Ada, …" / "Ada — …").
    out = _WILLIAM_ADDR_RE.sub(lambda m: f"{name}{m.group(1)}", text)
    out = _WILLIAM_WORD_RE.sub(name, out)
    return out


def _paragraph_is_william_only(
    para: str, flags: dict[str, bool]
) -> bool:
    """True when paragraph is seed-specific injury/context the athlete lacks."""
    if not para.strip():
        return False
    if _ISJAS_RE.search(para) and not flags.get("rygg_isjas"):
        return True
    if _FINGER_RE.search(para) and not flags.get("finger"):
        return True
    return False


def _strip_william_only_lines(para: str, flags: dict[str, bool]) -> str:
    """Within a mixed paragraph, drop lines that are William-injury-only."""
    lines = para.splitlines()
    kept: list[str] = []
    for line in lines:
        if _ISJAS_RE.search(line) and not flags.get("rygg_isjas"):
            continue
        if _FINGER_RE.search(line) and not flags.get("finger"):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def personalize_coach_text(
    text: str,
    athlete: dict[str, Any] | None = None,
) -> str:
    """Rewrite library coach markdown for the active athlete."""
    if not text:
        return text
    athlete = athlete or {}
    name = athlete_display_name(athlete)
    flags = athlete_injury_flags(athlete)

    # Keep Intervals syntax / ZWO bodies after the coach separator intact.
    coach_part = text
    intervals_part = ""
    if "\n---\n" in text and "### Fra treneren" in text:
        # format_planned_session_for_intervals: coach + --- + intervals
        head, tail = text.split("\n---\n", 1)
        coach_part = head
        intervals_part = tail
    elif "\n---intervals---\n" in text:
        head, tail = text.split("\n---intervals---\n", 1)
        coach_part = head
        intervals_part = "---intervals---\n" + tail

    coach_part = replace_william_addressee(coach_part, name)

    paragraphs = re.split(r"\n\s*\n", coach_part)
    kept_paras: list[str] = []
    for para in paragraphs:
        if _paragraph_is_william_only(para, flags):
            # Salvage a trailing Plan B if the rest is injury-only.
            plan_b = re.search(r"(Plan B:[^\n]+)", para, re.IGNORECASE)
            if plan_b and not _ISJAS_RE.search(plan_b.group(1)):
                kept_paras.append(plan_b.group(1).strip())
            continue
        cleaned = _strip_william_only_lines(para, flags)
        if cleaned:
            kept_paras.append(cleaned)

    # Soft profile cue when athlete has injuries but we stripped seed copy.
    injury_notes = (athlete.get("injury_notes") or "").strip()
    if injury_notes and not flags.get("rygg_isjas") and not flags.get("finger"):
        cue = f"Profil-merke (skade/plager): {injury_notes[:240]}"
        if cue not in "\n\n".join(kept_paras):
            kept_paras.append(cue)

    out = "\n\n".join(kept_paras).strip()
    # Collapse excess blank lines
    out = re.sub(r"\n{3,}", "\n\n", out)
    if intervals_part:
        # head already includes "### Fra treneren\n\n…"
        if out and not out.endswith("\n"):
            out = out + "\n"
        return f"{out}\n---\n\n{intervals_part.lstrip()}" if out else (
            f"---\n\n{intervals_part.lstrip()}"
        )
    return out


def personalize_title(
    title: str,
    athlete: dict[str, Any] | None = None,
) -> str:
    if not title:
        return title
    name = athlete_display_name(athlete)
    flags = athlete_injury_flags(athlete)
    out = replace_william_addressee(title, name)
    if not flags.get("rygg_isjas"):
        out = _TITLE_ISJAS_RE.sub("", out)
        out = re.sub(r"\s{2,}", " ", out).strip(" —-")
        # "Styrke prehab  (ST04)" → keep code, drop empty gap
        out = re.sub(r"\s+\(", " (", out)
    return out.strip() or title


def injury_strength_session(
    athlete: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Title + planned path for injury-week strength (not always ST04 isjas)."""
    flags = athlete_injury_flags(athlete)
    if flags.get("rygg_isjas"):
        return (
            "Styrke prehab rygg/isjas (ST04)",
            "workouts/planned/strength/ST04-prehab-rygg-isjas-hjemme.txt",
        )
    return (
        "Styrke recovery / prehab (ST03)",
        "workouts/planned/strength/ST03-recovery-hjemme.txt",
    )


def personalize_icu_event(
    ev: dict[str, Any],
    athlete: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mutate ICU WORKOUT event name/description for the active athlete."""
    if not ev:
        return ev
    desc = ev.get("description")
    if isinstance(desc, str) and desc.strip():
        ev["description"] = personalize_coach_text(desc, athlete)
    name = ev.get("name")
    if isinstance(name, str) and name.strip():
        ev["name"] = personalize_title(name, athlete)
    return ev


def text_has_william_addressee(text: str) -> bool:
    """True if coach text still addresses William by name."""
    return bool(_WILLIAM_WORD_RE.search(text or ""))
