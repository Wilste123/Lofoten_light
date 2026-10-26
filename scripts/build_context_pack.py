#!/usr/bin/env python3
"""Build a single context pack from the agent-modus (uke1-bakke) tree.

Deterministic grounding for coach turns — no RAG/MCP:
  - docs/athlete/* (profil, mål, TB-config, plager)
  - docs/coach/agent-modus-pilot (kort)
  - nyeste ukeplan under plans/
  - nøkkeløkter (f.eks. R-HILL-5x2) + workouts/index snutt
  - Intervals nær-vindu (lokal CSV eller --fetch-icu)
  - TB-Score via compute_readiness når CSV finnes

Output: data/context/context-pack.md (+ optional .json)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATHLETE = ROOT / "docs" / "athlete"
COACH_DOCS = ROOT / "docs" / "coach"
PLANS = ROOT / "plans"
WORKOUTS = ROOT / "workouts"
ICU_DIR = ROOT / "data" / "intervals" / "exports"
OUT_DIR = ROOT / "data" / "context"
OUT_MD = OUT_DIR / "context-pack.md"
OUT_JSON = OUT_DIR / "context-pack.json"

WEEK_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-uke-(\d+)\.md$")
# Prefer dated week files; skip month/block overviews for "denne uke"
WEEK_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-uke", re.I)

ATHLETE_FILES = (
    "profile.md",
    "goals.md",
    "plager-rygg-isjas.md",
    "soner-planlegging-2026.md",
    "readiness-totalbelastning.md",
    "readiness-config.json",
    "kroppssammensetning-smartvekt.md",
    "gemini-brief.md",
)

KEY_WORKOUTS = (
    WORKOUTS / "planned" / "run" / "R-HILL-5x2-reetablering.txt",
    WORKOUTS / "planned" / "run" / "OPV-myr-loping-staver.txt",
    WORKOUTS / "planned" / "run" / "OPV-elghufs-5x4.txt",
)


def _read(path: Path, max_chars: int | None = None) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + f"\n\n… [truncated @ {max_chars} chars]\n"
    return text


def latest_week_plan() -> Path | None:
    candidates: list[tuple[date, int, Path]] = []
    for p in PLANS.glob("*-*-*-uke*.md"):
        if not WEEK_NAME_RE.match(p.name):
            continue
        m = WEEK_RE.match(p.name)
        if m:
            try:
                start = date.fromisoformat(m.group(1))
                week = int(m.group(2))
            except ValueError:
                continue
            candidates.append((start, week, p))
            continue
        # e.g. 2026-10-19-uke-build.md
        try:
            start = date.fromisoformat(p.name[:10])
        except ValueError:
            continue
        candidates.append((start, 0, p))
    if not candidates:
        return None
    candidates.sort(key=lambda t: (t[0], t[1]))
    return candidates[-1][2]


def _run_fetch(script: str, days: int, output: Path) -> bool:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / script),
        "--days",
        str(days),
        "-o",
        str(output),
    ]
    try:
        r = subprocess.run(cmd, cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True)
    except OSError as e:
        print(f"fetch failed ({script}): {e}", file=sys.stderr)
        return False
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        print(f"fetch failed ({script}): {err}", file=sys.stderr)
        return False
    return output.is_file()


def fetch_icu(days: int) -> dict[str, Path | None]:
    ICU_DIR.mkdir(parents=True, exist_ok=True)
    act = ICU_DIR / f"pack-activities-{days}d.csv"
    wel = ICU_DIR / f"pack-wellness-{days}d.csv"
    ok_a = _run_fetch("fetch_intervals_activities.py", days, act)
    ok_w = _run_fetch("fetch_intervals_wellness.py", days, wel)
    return {
        "activities": act if ok_a else None,
        "wellness": wel if ok_w else None,
    }


def find_local_icu() -> dict[str, Path | None]:
    if not ICU_DIR.is_dir():
        return {"activities": None, "wellness": None}

    def newest(patterns: tuple[str, ...]) -> Path | None:
        files: list[Path] = []
        for pat in patterns:
            files.extend(ICU_DIR.glob(pat))
        files = [f for f in files if f.is_file() and f.stat().st_size > 0]
        if not files:
            return None
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files[0]

    return {
        "activities": newest(
            ("pack-activities-*.csv", "*activit*.csv", "uke*.csv", "*-activities*.csv")
        ),
        "wellness": newest(
            ("pack-wellness-*.csv", "*wellness*.csv", "wellness-latest.csv")
        ),
    }


def csv_preview(path: Path | None, max_lines: int = 35) -> str | None:
    if path is None or not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    head = lines[:max_lines]
    more = len(lines) - len(head)
    body = "\n".join(head)
    if more > 0:
        body += f"\n… [{more} more lines in {path.name}]"
    return f"Fil: `{path.relative_to(ROOT)}`\n\n```csv\n{body}\n```"


def try_tb_score(icu: dict[str, Path | None]) -> str | None:
    """Run compute_readiness when wellness (+ activities) CSVs exist."""
    wel = icu.get("wellness")
    if wel is None or not wel.is_file():
        return None
    cmd = [sys.executable, str(ROOT / "scripts" / "compute_readiness.py"), str(wel), "--json"]
    act = icu.get("activities")
    if act is not None and act.is_file():
        cmd.extend(["--activities", str(act)])
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"**TB-Score feilet:** {e}\n"
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()[:500]
        return f"**TB-Score feilet:** {err}\n"
    out = (r.stdout or "").strip()
    if not out:
        return None
    # Prefer markdown path if script also printed non-json — try parse JSON
    try:
        data = json.loads(out)
        pretty = json.dumps(data, indent=2, ensure_ascii=False)
        if len(pretty) > 6000:
            pretty = pretty[:6000] + "\n… [truncated]\n"
        return f"```json\n{pretty}\n```\n"
    except json.JSONDecodeError:
        # stdout may be markdown
        text = out
        if len(text) > 6000:
            text = text[:6000] + "\n… [truncated]\n"
        return text + "\n"


def build_pack(*, fetch: bool, days: int, max_section: int) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sections: list[dict] = []
    missing: list[str] = []

    # 1. Athlete
    athlete_parts: list[str] = []
    for name in ATHLETE_FILES:
        p = ATHLETE / name
        text = _read(p, max_section)
        if text is None:
            missing.append(f"athlete:{name}")
            continue
        athlete_parts.append(f"### {name}\n\n{text.strip()}\n")
    if athlete_parts:
        sections.append(
            {
                "id": "athlete",
                "title": "1. Athlete snapshot (profil / mål / TB / avtaler)",
                "body": "\n".join(athlete_parts),
            }
        )
    else:
        missing.append("athlete:all")

    # 2. Agent-modus pilot (short)
    pilot = COACH_DOCS / "agent-modus-pilot-2026-10.md"
    ptext = _read(pilot, min(max_section, 8000))
    if ptext:
        sections.append(
            {
                "id": "agent_modus",
                "title": "2. Agent-modus pilot (arbeidsmodell)",
                "body": f"Kilde: `{pilot.relative_to(ROOT)}`\n\n{ptext.strip()}\n",
            }
        )
    else:
        missing.append("docs/coach/agent-modus-pilot")

    # 3. Week plan
    week = latest_week_plan()
    if week:
        wtext = _read(week, max_section) or ""
        sections.append(
            {
                "id": "week_plan",
                "title": "3. Denne uke (plan)",
                "body": f"Kilde: `{week.relative_to(ROOT)}`\n\n{wtext.strip()}\n",
                "path": str(week.relative_to(ROOT)),
            }
        )
    else:
        missing.append("plans:week")

    # 4. Key workouts
    wo_parts: list[str] = []
    idx = _read(WORKOUTS / "index.md", 2500)
    if idx:
        wo_parts.append(f"### workouts/index.md\n\n{idx.strip()}\n")
    for kp in KEY_WORKOUTS:
        kt = _read(kp, 2500)
        if kt:
            wo_parts.append(f"### {kp.relative_to(ROOT)}\n\n{kt.strip()}\n")
        else:
            missing.append(f"workout:{kp.name}")
    if wo_parts:
        sections.append(
            {
                "id": "key_workouts",
                "title": "4. Nøkkeløkter (bibliotek)",
                "body": "\n".join(wo_parts),
            }
        )

    # 5. ICU + TB
    icu = fetch_icu(days) if fetch else find_local_icu()
    icu_ok = bool(icu.get("activities") or icu.get("wellness"))
    icu_blocks: list[str] = []
    for label, key in (("Activities", "activities"), ("Wellness", "wellness")):
        preview = csv_preview(icu.get(key))
        if preview:
            icu_blocks.append(f"### {label}\n\n{preview}\n")
        else:
            missing.append(f"icu:{key}")

    tb = try_tb_score(icu)
    if tb:
        icu_blocks.append(f"### TB-Score (compute_readiness)\n\n{tb}")
    else:
        missing.append("tb:score")

    if icu_blocks and icu_ok:
        body = "\n".join(icu_blocks)
    elif icu_blocks:
        body = (
            "**ICU CSV mangler delvis.** Sett `INTERVALS_API` og kjør "
            f"`python3 scripts/build_context_pack.py --fetch-icu --days {days}`.\n\n"
            + "\n".join(icu_blocks)
        )
    else:
        body = (
            "**ICU mangler.** Sett `INTERVALS_API` / `INTERVALS_API_KEY` og kjør "
            f"`python3 scripts/build_context_pack.py --fetch-icu --days {days}`, "
            "eller legg CSV i `data/intervals/exports/`.\n"
        )
    sections.append(
        {
            "id": "icu_tb",
            "title": f"5. Intervals nær-vindu (~{days}d) + TB/load",
            "body": body,
        }
    )

    sections.append(
        {
            "id": "coach_rules",
            "title": "6. Hard grounding-regel",
            "body": (
                "- Svar må referere konkrete felter fra denne packen "
                "(økter, TB/load, avtaler, FTP/soner, ukeplan) **eller** si ærlig «mangler data».\n"
                "- Ingen generisk VO₂-/PT-essay.\n"
                "- Historisk FTP 410 W (2019) er **ikke** nåværende intensitet.\n"
                "- Arbeidsmodell (pilot): plan i TP; fakta fra Intervals + denne repo-treet.\n"
            ),
        }
    )

    md_parts = [
        "# Context pack — Lofoten coach (agent-modus tree)",
        "",
        f"- Generert: `{now}`",
        f"- Base: `rethink` ← `cursor/uke1-bakke-5x2-tor-634c`",
        f"- ICU fetch forsøkt: `{fetch}`",
        f"- ICU ok: `{icu_ok}`",
        f"- Manglende kilder: `{', '.join(missing) if missing else '(ingen)'}`",
        "",
        "Bruk: les denne fila før coach-svar om uke / i morgen / load / TB.",
        "",
    ]
    for sec in sections:
        md_parts.append(f"## {sec['title']}")
        md_parts.append("")
        md_parts.append(sec["body"].rstrip())
        md_parts.append("")

    return {
        "generated_at": now,
        "base_branch": "cursor/uke1-bakke-5x2-tor-634c",
        "icu_ok": icu_ok,
        "missing": missing,
        "week_plan": str(week.relative_to(ROOT)) if week else None,
        "icu_files": {
            k: (str(v.relative_to(ROOT)) if v else None) for k, v in icu.items()
        },
        "markdown": "\n".join(md_parts).rstrip() + "\n",
        "sections": [{"id": s["id"], "title": s["title"]} for s in sections],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build coach context pack from agent-modus tree (MD ± JSON)"
    )
    parser.add_argument(
        "--fetch-icu",
        action="store_true",
        help="Fetch Intervals activities+wellness (needs INTERVALS_API)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=14,
        help="Near-window days for ICU (default 14)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help=f"Also write {OUT_JSON.relative_to(ROOT)}",
    )
    parser.add_argument(
        "--max-section-chars",
        type=int,
        default=12000,
        help="Truncate each source file (default 12000)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=OUT_MD,
        help=f"Markdown output (default {OUT_MD.relative_to(ROOT)})",
    )
    args = parser.parse_args()

    pack = build_pack(
        fetch=args.fetch_icu,
        days=args.days,
        max_section=args.max_section_chars,
    )

    out_md: Path = args.output
    if not out_md.is_absolute():
        out_md = ROOT / out_md
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(pack["markdown"], encoding="utf-8")
    print(f"Wrote {out_md.relative_to(ROOT)} (icu_ok={pack['icu_ok']})")

    if args.json:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        payload = {k: v for k, v in pack.items() if k != "markdown"}
        payload["markdown_path"] = str(out_md.relative_to(ROOT))
        OUT_JSON.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {OUT_JSON.relative_to(ROOT)}")

    if pack["missing"]:
        print("Missing: " + ", ".join(pack["missing"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
