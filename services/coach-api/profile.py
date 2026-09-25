"""Write athlete profile markdown (docs/athlete/profile.md style)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _fmt(val: Any, empty: str = "—") -> str:
    if val is None or val == "":
        return empty
    return str(val)


def render_profile_md(athlete: dict[str, Any]) -> str:
    """Render a profile.md body for any athlete (not William-specific)."""
    name = athlete.get("display_name") or "Utøver"
    coach = athlete.get("coach_display_name") or "Trener"
    agreements = athlete.get("agreements") or []
    if isinstance(agreements, str):
        agreements = []
    agr_lines = (
        "\n".join(f"- {a}" for a in agreements)
        if agreements
        else "- (ingen lagrede avtaler ennå)"
    )
    ftp = athlete.get("ftp_tested")
    ftp_at = athlete.get("ftp_tested_at")
    ftp_line = f"**{ftp} W**" if ftp else "*ikke satt*"
    if ftp and ftp_at:
        ftp_line += f" ({ftp_at})"

    ibs_map = {"no": "Nei", "yes": "Ja", "unsure": "Usikker"}
    gluten_map = {
        "none": "Ingen restriksjon",
        "sensitive": "Sensitivitet",
        "celiac": "Cøliaki",
    }
    ibs = ibs_map.get(athlete.get("nutrition_ibs") or "no", athlete.get("nutrition_ibs"))
    gluten = gluten_map.get(
        athlete.get("nutrition_gluten") or "none", athlete.get("nutrition_gluten")
    )
    lactose = "Ja" if athlete.get("nutrition_lactose") else "Nei"

    return f"""# Athlete profile — {name}

Kilde for sannhet for coach (app + Cursor). Oppdateres ved onboarding og når Du-fanen lagres.

## Om {name}

### Profil

| | |
|---|---|
| Visningsnavn | {name} |
| Sport | {_fmt(athlete.get("sport"), "triathlon")} |
| Tidssone | {_fmt(athlete.get("timezone"), "Europe/Oslo")} |
| Alder | {_fmt(athlete.get("age_years"))} |
| Vekt (kg) | {_fmt(athlete.get("weight_kg"))} |
| Tilgjengelighet | {_fmt(athlete.get("schedule_notes"), "(ikke satt)")} |

### Trener (app)

| | |
|---|---|
| Trenernavn | {coach} |
| Personlighet | {_fmt(athlete.get("coach_personality"), "direkte")} |
| Stil-notat | {_fmt(athlete.get("coach_style_note"), "(ingen)")} |
| Aksentfarge | {_fmt(athlete.get("accent_color"), "#1a6b4a")} |

## Mål

{_fmt(athlete.get("goal_text"), "(ikke satt)")}

## Ukens fokus

{_fmt(athlete.get("weekly_focus"), "(ikke satt)")}

## Form

| Metrikk | Verdi |
|---------|-------|
| Testet FTP | {ftp_line} |
| Estimert FTP | {_fmt(athlete.get("ftp_estimated"), "venter på ≥5 sykkeløkter med watt")} |
| VO₂-estimat | {_fmt(athlete.get("vo2_estimate"), "—")} |
| Estimate confidence | {_fmt(athlete.get("estimate_confidence"))} |

## Begrensninger / skade

{_fmt(athlete.get("injury_notes"), "(ingen notert)")}

## Ernæring / mage-tarm

| | |
|---|---|
| IBS | {ibs} |
| Gluten | {gluten} |
| Laktose | {lactose} |
| Andre restriksjoner | {_fmt(athlete.get("nutrition_other_restrictions"), "(ingen)")} |
| Notater | {_fmt(athlete.get("nutrition_notes"), "(ingen)")} |

**Viktig:** Tilpass råd ut fra feltene over og `knowledge/ernaring/`. **Aldri diagnostiser.** Ved usikkerhet: henvis til lege / klinisk ernæringsfysiolog.

## Avtaler

{agr_lines}

## Notater

{_fmt(athlete.get("notes"), "(ingen)")}

## Coaching notes (for agenten)

- Tilpass råd til **{name}** — ikke anta Williams historikk (FTP 410, NTG, osv.) med mindre det står her.
- Trenerstemme: **{coach}**, personlighet «{_fmt(athlete.get("coach_personality"), "direkte")}».
- Respekter ernæring/GI-feltene; bruk `knowledge/ernaring/` generelt.
- Intervals.icu eier øktdetaljer; denne filen eier menneskelig kontekst.
"""


def write_profile(athletes_dir: Path, athlete: dict[str, Any]) -> Path:
    """Write data/athletes/{id}/profile.md and return path."""
    athlete_id = athlete["id"]
    dest_dir = athletes_dir / athlete_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / "profile.md"
    path.write_text(render_profile_md(athlete), encoding="utf-8")
    return path


def load_profile_md(
    athletes_dir: Path, athlete: dict[str, Any], *, max_chars: int = 14000
) -> str:
    """Prefer on-disk profile.md (seed/onboarding); fall back to render from SQLite.

    Chat/overview context must include agreements and injury notes from the file
    when present (e.g. after seed_from_repo).
    """
    athlete_id = athlete.get("id") or ""
    path = athletes_dir / athlete_id / "profile.md" if athlete_id else None
    if path and path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            if len(text) > max_chars:
                return text[: max_chars - 20] + "\n\n[…trimmet…]"
            return text
    return render_profile_md(athlete)
