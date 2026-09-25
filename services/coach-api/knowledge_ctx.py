"""Load trimmed knowledge snippets for chat context."""

from __future__ import annotations

from pathlib import Path

# Prefer short, high-signal files for the system prompt budget
COACH_FILES = [
    "coach/coach-filosofi.md",
    "coach/treneridentitet.md",
    "coach/ole-grenser.md",
]
ERNARING_FILES = [
    "ernaring/coach-chat-kort.md",
    "ernaring/ibs-og-gluten.md",
]


def _read_trimmed(path: Path, max_chars: int) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n\n[…trimmet…]"


def load_knowledge_bundle(
    knowledge_dir: Path,
    *,
    coach_budget: int = 3500,
    ernaring_budget: int = 2500,
) -> str:
    parts: list[str] = []
    per_coach = coach_budget // max(len(COACH_FILES), 1)
    for rel in COACH_FILES:
        chunk = _read_trimmed(knowledge_dir / rel, per_coach)
        if chunk:
            parts.append(f"### {rel}\n{chunk}")
    per_ern = ernaring_budget // max(len(ERNARING_FILES), 1)
    for rel in ERNARING_FILES:
        chunk = _read_trimmed(knowledge_dir / rel, per_ern)
        if chunk:
            parts.append(f"### {rel}\n{chunk}")
    return "\n\n".join(parts)
