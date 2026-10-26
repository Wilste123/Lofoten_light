"""Server-side knowledge-first context pack for Fly coach chat.

Mirrors rethink ``scripts/build_context_pack.py`` *ideas* (SOURCES/RULES +
athlete + knowledge kjerne) without requiring the CLI or ICU CSV on disk.
Live load/plan comes from the chat overview_stub (Intervals already in API).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config

# Core method files — same spirit as rethink pack §6 (capped).
_KNOWLEDGE_SNIPPETS: list[tuple[str, int]] = [
    ("README.md", 2500),
    ("coach/coach-filosofi.md", 3500),
    ("coach/treneridentitet.md", 2500),
    ("coach/ukemaler.md", 3000),
    ("coach/kvalitetsnorm-toppidrett.md", 2500),
    ("load-and-intensity.md", 2500),
]

# Optional athlete docs when present next to REPO_ROOT (Docker / local).
_ATHLETE_DOCS: list[tuple[str, int]] = [
    ("profile.md", 4000),
    ("goals.md", 2500),
    ("plager-rygg-isjas.md", 2500),
    ("soner-planlegging-2026.md", 2500),
]

KNOWLEDGE_FIRST_HEADER = """## SOURCES / RULES (hard)

**Allowed sources only:**
- Athlete profile / DB snapshot / agreements / injury notes
- `knowledge/` (metode) — snippets below + adaptive knowledge section
- App plan + Intervals near-window in overview snapshot
- User message (and this chat thread)

**Forbidden:** web search, browsing, generiske internett-coaching-påstander,
«det folk sier online» uten at det allerede ligger i knowledge/athlete.

Hvis noe mangler i tillatte kilder: skriv **«mangler»** — ikke fyll fra nettet.
Historisk FTP 410 W (2019) er **ikke** dagens intensitet.
""".strip()


def _read_capped(path: Path, max_chars: int) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if len(text) > max_chars:
        return text[:max_chars] + f"\n\n… [truncated @ {max_chars} chars]\n"
    return text


def _athlete_docs_dir() -> Path:
    root = Path(config.REPO_ROOT)
    # Docker: docs/athlete next to API; local: repo root
    candidates = [
        root / "docs" / "athlete",
        Path(config.REPO_ROOT) / "docs" / "athlete",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return root / "docs" / "athlete"


def build_context_pack(
    knowledge_dir: Path | str,
    *,
    athlete: dict[str, Any] | None = None,
    overview_stub: dict[str, Any] | None = None,
    include_overview_json: bool = True,
    max_overview_chars: int = 6000,
) -> dict[str, Any]:
    """Build pack markdown + meta for system prompt / GET /v1/context/pack."""
    kdir = Path(knowledge_dir)
    missing: list[str] = []
    paths_used: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

    parts: list[str] = [
        "# Context pack — Lofoten coach (Fly / coach-api)",
        "",
        KNOWLEDGE_FIRST_HEADER,
        "",
        f"- Generert: `{now}`",
        "- Kilde: knowledge/ + athlete docs (disk) + chat overview (ICU/plan)",
        "",
    ]

    # Athlete summary from DB row (always — not William-locked)
    ath = athlete or {}
    if ath:
        agr = ath.get("agreements") or []
        agr_s = "; ".join(str(a) for a in agr[:12]) if agr else "(ingen)"
        parts.extend(
            [
                "## 1. Athlete (DB)",
                "",
                f"- Navn: {ath.get('display_name') or '(mangler)'}",
                f"- Mål: {(ath.get('goal_text') or '(mangler)')[:400]}",
                f"- Type: {ath.get('athlete_type') or '(mangler)'} | "
                f"økter/uke: {ath.get('sessions_per_week') or '(mangler)'}",
                f"- Skade: {(ath.get('injury_notes') or '(ingen)')[:400]}",
                f"- Form/fokus: {(ath.get('fitness_notes') or '(ingen)')[:300]}",
                f"- Schedule: {(ath.get('schedule_notes') or '(ingen)')[:300]}",
                f"- Avtaler: {agr_s}",
                f"- FTP testet: {ath.get('ftp_tested') or '(mangler)'}",
                "",
            ]
        )
    else:
        missing.append("athlete:db")

    # Optional on-disk athlete docs
    docs_dir = _athlete_docs_dir()
    doc_blocks: list[str] = []
    for name, cap in _ATHLETE_DOCS:
        p = docs_dir / name
        text = _read_capped(p, cap)
        if text:
            rel = f"docs/athlete/{name}"
            paths_used.append(rel)
            doc_blocks.append(f"### {rel}\n\n{text.strip()}\n")
        else:
            missing.append(f"athlete_doc:{name}")
    if doc_blocks:
        parts.append("## 2. Athlete docs (disk)")
        parts.append("")
        parts.extend(doc_blocks)
    else:
        parts.append("## 2. Athlete docs (disk)")
        parts.append("")
        parts.append("*(mangler på disk — bruk DB-profil + seeded profile.md)*")
        parts.append("")

    # Knowledge snippets
    kn_blocks: list[str] = []
    for rel, cap in _KNOWLEDGE_SNIPPETS:
        p = kdir / rel
        text = _read_capped(p, cap)
        if text:
            paths_used.append(f"knowledge/{rel}")
            kn_blocks.append(f"### knowledge/{rel}\n\n{text.strip()}\n")
        else:
            missing.append(f"knowledge:{rel}")
    parts.append("## 3. Knowledge (metode — ikke internett)")
    parts.append("")
    if kn_blocks:
        parts.append(
            "Råd om *hvordan* trene skal forankres her — **ikke** fra web search.\n"
        )
        parts.extend(kn_blocks)
    else:
        parts.append("**mangler** knowledge-filer under KNOWLEDGE_DIR.")
        parts.append("")

    # Overview / ICU / plan from live chat context
    parts.append("## 4. Overview snapshot (app + Intervals)")
    parts.append("")
    if overview_stub and include_overview_json:
        blob = json.dumps(overview_stub, ensure_ascii=False, default=str)
        if len(blob) > max_overview_chars:
            blob = blob[:max_overview_chars] + f"… [truncated @ {max_overview_chars}]"
        parts.append("```json")
        parts.append(blob)
        parts.append("```")
        parts.append("")
    else:
        missing.append("overview")
        parts.append("*(mangler overview — chat bygger dette per request)*")
        parts.append("")

    parts.append("## 5. Hard grounding")
    parts.append("")
    parts.append(
        "- Knowledge-first: athlete + knowledge + snapshot + melding. **Ikke** web.\n"
        "- Referer konkrete felter (økter, load, avtaler, FTP/soner) **eller** si «mangler».\n"
        "- Ingen generisk VO₂-/PT-essay.\n"
    )

    markdown = "\n".join(parts).rstrip() + "\n"
    return {
        "generated_at": now,
        "markdown": markdown,
        "missing": missing,
        "paths_used": paths_used,
        "chars": len(markdown),
    }


def pack_for_system_prompt(
    knowledge_dir: Path | str,
    *,
    athlete: dict[str, Any] | None = None,
    overview_stub: dict[str, Any] | None = None,
    max_chars: int = 14000,
) -> str:
    """Compact pack block for injection into build_system_prompt."""
    pack = build_context_pack(
        knowledge_dir,
        athlete=athlete,
        overview_stub=overview_stub,
        # Overview already appears as JSON later in the prompt — skip duplicate bulk.
        include_overview_json=False,
    )
    md = pack["markdown"]
    if len(md) > max_chars:
        md = md[:max_chars] + f"\n\n… [pack truncated @ {max_chars} chars]\n"
    return md
