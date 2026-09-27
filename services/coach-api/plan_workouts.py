"""Plan → Intervals workouts via the **existing** økt-bygger (CLI ground truth).

Structure / ICU payload
-----------------------
Reuses ``scripts/intervals_push_calendar.build_workout_event`` +
``scripts/intervals_lib`` (ZWO ``file_contents``, planned session Intervals
syntax, strength txt, sport types, moving_time, targets). Same event shape
as ``python3 scripts/intervals_push_calendar.py``.

Prescription / content
----------------------
Knowledge-templated first 1–2 weeks: picks real ``workouts/planned/**`` library
sessions by athlete signals (beginner / returning / injury / time-constrained),
aligned with ``knowledge/coach/ukemaler.md`` + conditional packs from
``knowledge_ctx.select_knowledge_paths``. No parallel ad-hoc WORKOUT stub.

Web sync still uses preview → pending → confirm; external ids ``ll-coach-w-…``
so Plan-tab withdraw stays scoped (CLI seed uses ``ll-agent-…``).
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

import config
from athlete_type import infer_athlete_type
from intervals_calendar import (
    WORKOUT_EXTERNAL_PREFIX,
    build_block_note_events,
    external_id_for_workout,
    parse_iso_date,
    public_event_preview,
)
from knowledge_ctx import detect_athlete_signals, select_knowledge_paths
from workout_personalize import (
    injury_strength_session,
    personalize_icu_event,
    personalize_title,
)


def format_exc_nb(exc: BaseException) -> str:
    """Human-readable Norwegian-facing error (never bare errno like «2»)."""
    name = type(exc).__name__
    if isinstance(exc, KeyError):
        key = exc.args[0] if exc.args else "?"
        return f"{name} for felt/nøkkel {key!r}"
    if isinstance(exc, IndexError):
        idx = exc.args[0] if exc.args else "?"
        return (
            f"{name} for indeks {idx!r} "
            "(ofte Path.parents i Docker /app — sjekk _ancestor_paths)"
        )
    if isinstance(exc, FileNotFoundError):
        path = getattr(exc, "filename", None) or (
            exc.args[1] if len(exc.args) > 1 else str(exc)
        )
        return f"Mangler fil/mappe: {path}"
    if isinstance(exc, ModuleNotFoundError):
        mod = getattr(exc, "name", None) or str(exc)
        return f"Mangler Python-modul «{mod}» (sjekk Docker COPY av repo_scripts/)"
    if isinstance(exc, ImportError):
        return f"Importfeil: {exc}"
    msg = str(exc).strip()
    if not msg or msg.isdigit():
        return f"{name}: {exc!r}"
    if len(msg) < 4 and not any(c.isalpha() for c in msg):
        return f"{name}: {exc!r}"
    return f"{name}: {msg}"


def _ancestor_paths(path: Path, max_up: int = 4) -> list[Path]:
    """Walk parents without IndexError when path is shallow (Docker ``/app``).

    ``Path('/app/x.py').parents[2]`` raises ``IndexError(2)`` — that broke Fly
    workout preview while notes still built.
    """
    out: list[Path] = []
    cur = path.resolve()
    for _ in range(max(0, max_up)):
        parent = cur.parent
        if parent == cur:
            break
        out.append(parent)
        cur = parent
    return out


DEFAULT_WORKOUT_WEEKS = 2

# Session row: weekday 0=Mon … 6=Sun, then CSV fields for build_workout_event
SessionSpec = tuple[int, str, str, str, int, int, str]
# (weekday, sport, subtype, title, duration_min, tss, planned_rel_path)


def signals_from_athlete(athlete: dict[str, Any] | None) -> dict[str, bool]:
    athlete = athlete or {}
    return detect_athlete_signals(
        "",
        draft={
            "goal_text": athlete.get("goal_text") or "",
            "injury_notes": athlete.get("injury_notes") or "",
            "schedule_notes": athlete.get("schedule_notes") or "",
            "background_notes": athlete.get("notes") or "",
            "notes": athlete.get("notes") or "",
            "athlete_type": athlete.get("athlete_type") or "",
            "sport": athlete.get("sport") or "",
            "coach_respect_notes": "",
        },
    )


def athlete_type_from_athlete(athlete: dict[str, Any] | None) -> str | None:
    athlete = athlete or {}
    if athlete.get("athlete_type"):
        return str(athlete["athlete_type"])
    info = infer_athlete_type(
        "",
        draft={
            "goal_text": athlete.get("goal_text") or "",
            "notes": athlete.get("notes") or "",
            "schedule_notes": athlete.get("schedule_notes") or "",
            "sport": athlete.get("sport") or "",
            "athlete_type": athlete.get("athlete_type") or "",
        },
        signals=signals_from_athlete(athlete),
    )
    return info["athlete_type"]


def knowledge_paths_for_workouts(
    athlete: dict[str, Any] | None = None,
    signals: dict[str, bool] | None = None,
) -> list[str]:
    """Same selection spirit as AI setup plan (ukemaler + conditional packs)."""
    athlete = athlete or {}
    atype = athlete_type_from_athlete(athlete)
    draft = {
        "goal_text": athlete.get("goal_text") or "",
        "injury_notes": athlete.get("injury_notes") or "",
        "schedule_notes": athlete.get("schedule_notes") or "",
        "background_notes": athlete.get("notes") or "",
        "notes": athlete.get("notes") or "",
        "athlete_type": atype or "",
        "sport": athlete.get("sport") or "",
    }
    # Nudge query blob when signals already known
    signals = signals or signals_from_athlete(athlete)
    bits = []
    if signals.get("beginner"):
        bits.append("nybegynner")
    if signals.get("returning"):
        bits.append("comeback pause tidligere")
    if signals.get("injury"):
        bits.append("skade rehab belastning ACWR")
    if signals.get("time_constrained"):
        bits.append("tidsklemma lite tid")
    if atype and ("runner" in atype or atype == "runner"):
        bits.append("løping halvmaraton maraton langtur")
    elif atype == "cyclist":
        bits.append("sykkel watt utholdenhet")
    elif atype == "swimmer":
        bits.append("svøm teknikk basseng")
    elif signals.get("multisport") or (
        atype in ("triathlete", "beginner_multi")
    ):
        bits.append("triatlon lofoten")
    return select_knowledge_paths(
        mode="plan",
        query_text=" ".join(bits),
        draft=draft,
    )


def _repo_scripts_dirs(*, module_file: Path | None = None) -> list[Path]:
    here_file = Path(module_file) if module_file else Path(__file__)
    here = here_file.resolve().parent
    roots: list[Path] = []
    for cand in (
        _workouts_root(module_file=here_file),
        here,
        *_ancestor_paths(here_file, max_up=4),
        Path(config.REPO_ROOT),
    ):
        if cand not in roots:
            roots.append(cand)
    dirs: list[Path] = []
    for root in roots:
        for name in ("scripts", "repo_scripts"):
            d = root / name
            if d not in dirs:
                dirs.append(d)
    dirs.append(here / "repo_scripts")
    return dirs


def _import_build_workout_event(
    *, module_file: Path | None = None
) -> Callable[..., dict]:
    """Load CLI builder — source of truth for Intervals WORKOUT shape."""
    last_err: Exception | None = None
    for d in _repo_scripts_dirs(module_file=module_file):
        if not (d / "intervals_push_calendar.py").is_file():
            continue
        path = str(d)
        if path not in sys.path:
            sys.path.insert(0, path)
        try:
            from intervals_push_calendar import build_workout_event  # type: ignore

            return build_workout_event
        except Exception as exc:  # pragma: no cover
            last_err = exc
            continue
    raise ImportError(
        "Kunne ikke importere scripts/intervals_push_calendar.build_workout_event "
        f"(sjekk at workouts/ + scripts er med i image). Sist feil: {last_err}"
    )


def _workouts_root(*, module_file: Path | None = None) -> Path:
    """Directory that contains workouts/planned and workouts/zwo.

    Never indexes ``Path.parents[n]`` directly — Docker copies the API to
    ``/app/*.py`` where ``parents[2]`` raises ``IndexError(2)``.
    """
    here_file = Path(module_file) if module_file else Path(__file__)
    candidates: list[Path] = [Path(config.REPO_ROOT)]
    for cand in _ancestor_paths(here_file, max_up=4):
        if cand not in candidates:
            candidates.append(cand)
    for cand in candidates:
        if (cand / "workouts" / "planned").is_dir() and (cand / "scripts").is_dir():
            return cand
        if (cand / "workouts" / "planned").is_dir() and (
            cand / "repo_scripts"
        ).is_dir():
            return cand
    return Path(config.REPO_ROOT)


def _phase_of_block(block: dict[str, Any]) -> str:
    raw = (
        str(block.get("phase") or "")
        + " "
        + str(block.get("theme") or "")
        + " "
        + str(block.get("title") or "")
    ).lower()
    if any(w in raw for w in ("rehab", "skånsom", "skansom", "skade")):
        return "rehab"
    if any(w in raw for w in ("etabler", "kontakt", "grunnlag", "vaner", "start")):
        return "etablering"
    if any(w in raw for w in ("build", "kvalitet", "utvikling")):
        return "build"
    if any(w in raw for w in ("peak", "spesifik", "målblokk", "mot mål")):
        return "peak"
    if any(w in raw for w in ("taper", "nedtrapp", "recovery", "restitusjon")):
        return "taper"
    return "base"


def _templates_for_signals(
    signals: dict[str, bool],
    *,
    phase: str,
    weekly_hours: float,
    athlete_type: str | None = None,
    athlete: dict[str, Any] | None = None,
) -> list[SessionSpec]:
    """Knowledge-aligned week from planned library (ukemaler-inspired).

    Paths are real ``workouts/planned/**`` files the CLI builder already resolves
    into ZWO / Intervals syntax / strength bodies. Injury strength picks ST04
    only when the athlete profile mentions rygg/isjas — otherwise ST03.
    """
    beginner = bool(signals.get("beginner"))
    injury = bool(signals.get("injury")) or phase == "rehab"
    time_c = bool(signals.get("time_constrained"))
    returning = bool(signals.get("returning"))
    atype = athlete_type or ""
    run_primary = atype.endswith("runner") or atype == "runner"
    bike_primary = atype == "cyclist"
    swim_primary = atype == "swimmer"
    inj_title, inj_path = injury_strength_session(athlete)

    # --- Run-primary (half/marathon/runner): no default swim/bike pack ---
    if run_primary and not injury:
        long_run = (
            "workouts/planned/run/R04-long-easy-75.txt"
            if weekly_hours >= 6
            else "workouts/planned/run/R02-easy-55-strides.txt"
        )
        long_min = 75 if weekly_hours >= 6 else 50
        long_tss = 70 if weekly_hours >= 6 else 45
        long_title = (
            "Løp long easy 75 (R04)" if weekly_hours >= 6 else "Løp easy + strides (R02)"
        )
        return [
            (0, "Run", "endurance", "Løp easy 40 (R01)", 40, 40,
             "workouts/planned/run/R01-easy-40.txt"),
            (1, "Strength", "general", "Styrke base (ST01)", 35, 20,
             "workouts/planned/strength/ST01-base.txt"),
            (2, "Run", "endurance", "Løp easy + strides (R02)", 50, 45,
             "workouts/planned/run/R02-easy-55-strides.txt"),
            (4, "Run", "endurance", "Løp trail/easy (R03)", 55, 50,
             "workouts/planned/run/R03-easy-trail-70.txt"),
            (5, "Run", "endurance", long_title, long_min, long_tss, long_run),
            (6, "Run", "recovery", "Løp recovery 30 (R01)", 30, 25,
             "workouts/planned/run/R01-recovery-30.txt"),
        ]

    if bike_primary and not injury:
        return [
            (0, "Bike", "recovery", "Sykkel recovery 45 (B01)", 45, 28,
             "workouts/planned/bike/recovery-spin-45.txt"),
            (1, "Strength", "general", "Styrke base (ST01)", 35, 20,
             "workouts/planned/strength/ST01-base.txt"),
            (2, "Bike", "endurance", "Sykkel Z2 90 (B02)", 90, 55,
             "workouts/planned/bike/endurance-90.txt"),
            (4, "Bike", "endurance", "Sykkel Z2 90 (B02)", 90, 55,
             "workouts/planned/bike/endurance-90.txt"),
            (5, "Bike", "endurance", "Sykkel Z2 120 (B03)", 120, 75,
             "workouts/planned/bike/endurance-120.txt"),
            (6, "Run", "recovery", "Løp recovery 30 (R01)", 30, 25,
             "workouts/planned/run/R01-recovery-30.txt"),
        ]

    if swim_primary and not injury:
        return [
            (0, "Swim", "technique", "Svøm teknikk A (S01)", 50, 35,
             "workouts/planned/swim/S01-teknikk-a.txt"),
            (1, "Strength", "general", "Styrke base (ST01)", 35, 20,
             "workouts/planned/strength/ST01-base.txt"),
            (2, "Swim", "endurance", "Svøm aerob 3×500 (S03)", 55, 45,
             "workouts/planned/swim/S03-aerob-3x500.txt"),
            (4, "Swim", "technique", "Svøm teknikk skulder (S02)", 40, 28,
             "workouts/planned/swim/S02-teknikk-skulder.txt"),
            (5, "Swim", "endurance", "Svøm aerob 1500 (S04)", 55, 45,
             "workouts/planned/swim/S04-aerob-1500.txt"),
            (6, "Run", "recovery", "Løp recovery 30 (R01)", 30, 25,
             "workouts/planned/run/R01-recovery-30.txt"),
        ]

    # --- Injury / ACWR-safe (skader/* + profile-matched prehab) ---
    if injury:
        if run_primary:
            return [
                (0, "Run", "recovery", "Løp recovery 30 (R01)", 30, 25,
                 "workouts/planned/run/R01-recovery-30.txt"),
                (2, "Strength", "general", inj_title, 35, 18, inj_path),
                (4, "Bike", "recovery", "Sykkel recovery 45 (B01)", 45, 28,
                 "workouts/planned/bike/recovery-spin-45.txt"),
                (6, "Run", "endurance", "Løp easy 40 (R01)", 40, 40,
                 "workouts/planned/run/R01-easy-40.txt"),
            ]
        return [
            (0, "Swim", "technique", "Svøm teknikk skulder (S02)", 40, 28,
             "workouts/planned/swim/S02-teknikk-skulder.txt"),
            (1, "Bike", "recovery", "Sykkel recovery 45 (B01)", 45, 28,
             "workouts/planned/bike/recovery-spin-45.txt"),
            (2, "Strength", "general", inj_title, 35, 18, inj_path),
            (4, "Swim", "recovery", "Svøm recovery (S09)", 35, 20,
             "workouts/planned/swim/S09-recovery.txt"),
            (5, "Bike", "endurance", "Sykkel Z2 90 (B02)", 90, 55,
             "workouts/planned/bike/endurance-90.txt"),
            (6, "Run", "recovery", "Løp recovery 30 (R01)", 30, 25,
             "workouts/planned/run/R01-recovery-30.txt"),
        ]

    # --- Beginner multisport / general: fewer sessions ---
    if beginner or (time_c and weekly_hours < 6):
        return [
            (0, "Swim", "technique", "Svøm teknikk A (S01)", 50, 35,
             "workouts/planned/swim/S01-teknikk-a.txt"),
            (1, "Run", "endurance", "Løp easy 40 (R01)", 40, 40,
             "workouts/planned/run/R01-easy-40.txt"),
            (2, "Bike", "recovery", "Sykkel recovery 45 (B01)", 45, 28,
             "workouts/planned/bike/recovery-spin-45.txt"),
            (3, "Strength", "general", "Styrke base (ST01)", 35, 20,
             "workouts/planned/strength/ST01-base.txt"),
            (5, "Run", "endurance", "Løp easy + strides (R02)", 50, 45,
             "workouts/planned/run/R02-easy-55-strides.txt"),
        ]

    # --- Time-constrained: konsistens, færre økter ---
    if time_c:
        return [
            (0, "Swim", "technique", "Svøm teknikk A (S01)", 50, 35,
             "workouts/planned/swim/S01-teknikk-a.txt"),
            (1, "Run", "endurance", "Løp easy + strides (R02)", 50, 45,
             "workouts/planned/run/R02-easy-55-strides.txt"),
            (2, "Bike", "endurance", "Sykkel Z2 90 (B02)", 90, 55,
             "workouts/planned/bike/endurance-90.txt"),
            (3, "Strength", "general", "Styrke base (ST01)", 35, 20,
             "workouts/planned/strength/ST01-base.txt"),
            (5, "Bike", "endurance", "Sykkel Z2 120 (B03)", 120, 75,
             "workouts/planned/bike/endurance-120.txt"),
        ]

    # --- Returning / base (ukemaler Fase A ≈ trainingdojo uke 1–2) ---
    if returning or phase in ("etablering", "base", "rehab"):
        long_bike = (
            "workouts/planned/bike/endurance-120.txt"
            if weekly_hours >= 8
            else "workouts/planned/bike/endurance-90.txt"
        )
        long_bike_min = 120 if weekly_hours >= 8 else 90
        long_bike_tss = 75 if weekly_hours >= 8 else 55
        long_title = (
            "Sykkel Z2 120 (B03)" if weekly_hours >= 8 else "Sykkel Z2 90 (B02)"
        )
        return [
            (0, "Swim", "technique", "Svøm teknikk A (S01)", 50, 35,
             "workouts/planned/swim/S01-teknikk-a.txt"),
            (1, "Run", "endurance", "Løp easy 40 (R01)", 40, 40,
             "workouts/planned/run/R01-easy-40.txt"),
            (2, "Bike", "endurance", "Sykkel Z2 90 (B02)", 90, 55,
             "workouts/planned/bike/endurance-90.txt"),
            (3, "Strength", "general", "Styrke base (ST01)", 35, 20,
             "workouts/planned/strength/ST01-base.txt"),
            (4, "Swim", "endurance", "Svøm aerob 3×500 (S03)", 55, 45,
             "workouts/planned/swim/S03-aerob-3x500.txt"),
            (5, "Bike", "endurance", long_title, long_bike_min, long_bike_tss, long_bike),
            (6, "Run", "endurance", "Løp easy + strides (R02)", 50, 45,
             "workouts/planned/run/R02-easy-55-strides.txt"),
        ]

    # --- Build / peak: still library sessions (no invented steps) ---
    return [
        (0, "Swim", "endurance", "Svøm aerob 1500 (S04)", 55, 45,
         "workouts/planned/swim/S04-aerob-1500.txt"),
        (1, "Run", "endurance", "Løp easy + strides (R02)", 50, 45,
         "workouts/planned/run/R02-easy-55-strides.txt"),
        (2, "Bike", "endurance", "Sykkel Z2 90 (B02)", 90, 55,
         "workouts/planned/bike/endurance-90.txt"),
        (3, "Strength", "general", "Styrke build (ST02)", 40, 22,
         "workouts/planned/strength/ST02-build.txt"),
        (4, "Swim", "technique", "Svøm teknikk A (S01)", 50, 35,
         "workouts/planned/swim/S01-teknikk-a.txt"),
        (5, "Bike", "endurance", "Sykkel Z2 120 (B03)", 120, 75,
         "workouts/planned/bike/endurance-120.txt"),
        (6, "Run", "endurance", "Løp long easy 75 (R04)", 75, 70,
         "workouts/planned/run/R04-long-easy-75.txt"),
    ]


def _anchor_start(blocks: list[dict[str, Any]], today: date | None = None) -> date | None:
    today = today or date.today()
    starts: list[date] = []
    for b in blocks:
        s = parse_iso_date(b.get("start_date"))
        e = parse_iso_date(b.get("end_date"))
        if not s:
            continue
        if e and e < today:
            continue
        starts.append(s)
    if not starts:
        for b in blocks:
            s = parse_iso_date(b.get("start_date"))
            if s:
                starts.append(s)
    if not starts:
        return None
    anchor = min(starts)
    if anchor < today:
        return today - timedelta(days=today.weekday())
    return anchor


def _block_for_day(blocks: list[dict[str, Any]], day: date) -> dict[str, Any] | None:
    for b in blocks:
        s = parse_iso_date(b.get("start_date"))
        e = parse_iso_date(b.get("end_date"))
        if s and e and s <= day <= e:
            return b
        if s and not e and s <= day:
            return b
    return blocks[0] if blocks else None


def _row_for_session(
    *,
    day_index: int,
    sport: str,
    subtype: str,
    title: str,
    duration: int,
    tss: int,
    planned: str,
    phase: str,
) -> dict[str, str]:
    """CSV-shaped row identical to plans/csv/trainingdojo-*.csv columns."""
    suffix = ""
    stem = Path(planned).stem.lower().replace("_", "")[:12]
    if sport.lower() == "strength":
        suffix = stem or "st"
    return {
        "day": str(day_index),
        "sport": sport,
        "subtype": subtype,
        "title": title,
        "duration_minutes": str(duration),
        "tss": str(tss),
        "description": planned,
        "phase": phase,
        "external_suffix": suffix,
        "start_time": "18:00" if sport.lower() == "strength" else "07:00",
    }


def build_plan_week_rows(
    blocks: list[dict[str, Any]],
    *,
    signals: dict[str, bool] | None = None,
    weeks: int = DEFAULT_WORKOUT_WEEKS,
    today: date | None = None,
    athlete: dict[str, Any] | None = None,
) -> tuple[date, list[dict[str, str]]]:
    """Produce trainingdojo-compatible CSV rows for first ``weeks`` microcycles."""
    if not blocks:
        return date.today(), []
    signals = signals or signals_from_athlete(athlete)
    atype = athlete_type_from_athlete(athlete)
    weeks = max(1, min(int(weeks or DEFAULT_WORKOUT_WEEKS), 2))
    anchor = _anchor_start(blocks, today=today)
    if not anchor:
        return date.today(), []
    week0 = anchor - timedelta(days=anchor.weekday())
    rows: list[dict[str, str]] = []
    for w in range(weeks):
        week_start = week0 + timedelta(days=7 * w)
        mid = week_start + timedelta(days=2)
        block = _block_for_day(blocks, mid) or blocks[0]
        try:
            wh = float(block.get("weekly_hours") or 8.0)
        except (TypeError, ValueError):
            wh = 8.0
        phase = _phase_of_block(block)
        specs = _templates_for_signals(
            signals,
            phase=phase,
            weekly_hours=wh,
            athlete_type=atype,
            athlete=athlete,
        )
        for weekday, sport, subtype, title, dur, tss, planned in specs:
            title = personalize_title(title, athlete)
            day = week_start + timedelta(days=weekday)
            owning = _block_for_day(blocks, day)
            if owning is None:
                continue
            bs = parse_iso_date(owning.get("start_date"))
            be = parse_iso_date(owning.get("end_date"))
            if bs and day < bs:
                continue
            if be and day > be:
                continue
            day_index = (day - week0).days + 1
            rows.append(
                _row_for_session(
                    day_index=day_index,
                    sport=sport,
                    subtype=subtype,
                    title=title,
                    duration=dur,
                    tss=tss,
                    planned=planned,
                    phase=phase,
                )
            )
    return week0, rows


def build_plan_week_icu_events(
    blocks: list[dict[str, Any]],
    *,
    signals: dict[str, bool] | None = None,
    weeks: int = DEFAULT_WORKOUT_WEEKS,
    today: date | None = None,
    athlete: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    module_file: Path | None = None,
) -> list[dict[str, Any]]:
    """ICU WORKOUT events via CLI ``build_workout_event`` (ZWO / planned syntax).

    Raises ImportError / OSError when the CLI builder or workouts library is
    missing from the runtime image — callers that must not 500 (setup preview)
    should catch and degrade.

    ``module_file`` is for tests that simulate Docker ``/app/*.py`` (shallow
    Path.parents); production leaves it None.
    """
    build_fn = _import_build_workout_event(module_file=module_file)
    root = Path(repo_root or _workouts_root(module_file=module_file))
    planned = root / "workouts" / "planned"
    if not planned.is_dir():
        raise FileNotFoundError(
            f"Mangler øktbibliotek under {root}/workouts/planned "
            "(Docker må COPY workouts/ — sjekk .dockerignore)."
        )
    plan_start, rows = build_plan_week_rows(
        blocks,
        signals=signals,
        weeks=weeks,
        today=today,
        athlete=athlete,
    )
    events: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        try:
            ev = build_fn(
                row,
                plan_start,
                row.get("start_time") or "07:00",
                {},  # bike ZWO resolved from planned txt zwo: line
                root,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Økt-bygger feilet for rad {i + 1} "
                f"({row.get('title') or row.get('sport') or '?'}): {format_exc_nb(exc)}"
            ) from exc
        # Stable web-coach ids (Plan-tab filter is ll-coach-*); keep builder fields.
        day = parse_iso_date(str(ev.get("start_date_local") or "")[:10])
        name = str(ev.get("name") or row.get("title") or "okt")
        if day:
            ev["external_id"] = external_id_for_workout(day, name, i)
        else:
            ev["external_id"] = f"{WORKOUT_EXTERNAL_PREFIX}row-{i}"
        ev["_day"] = str(ev.get("start_date_local") or "")[:10]
        ev["_sport"] = (row.get("sport") or "").lower()
        ev["_planned"] = row.get("description")
        ev["_has_zwo"] = bool(ev.get("file_contents"))
        try:
            ev["_duration_minutes"] = int(float(row.get("duration_minutes") or 0))
        except (TypeError, ValueError):
            ev["_duration_minutes"] = 0
        personalize_icu_event(ev, athlete)
        events.append(ev)
    return events


def _notes_only_bundle(
    blocks: list[dict[str, Any]],
    *,
    signals: dict[str, bool],
    weeks: int,
    error: str,
    athlete: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Degraded sync payload when library WORKOUT builder is unavailable."""
    note_events = build_block_note_events(blocks)
    note_previews = [public_event_preview(e) for e in note_events]
    k_paths = knowledge_paths_for_workouts(athlete, signals)
    return {
        "events": list(note_events),
        "note_events": note_events,
        "workout_events": [],
        "notes_count": len(note_events),
        "workouts_count": 0,
        "zwo_count": 0,
        "count": len(note_events),
        "notes_preview": note_previews,
        "workouts_preview": [],
        "events_preview": note_previews,
        "signals": {k: v for k, v in signals.items() if not str(k).startswith("_")},
        "knowledge_paths": k_paths,
        "weeks": weeks,
        "builder": "scripts/intervals_push_calendar.build_workout_event",
        "kind": "calendar_notes_only_degraded",
        "error": error,
        "description_no": (
            f"Grovplan-noter ({len(note_events)}) klar. "
            f"Øktbibliotek-forhåndsvisning feilet: {error}"
        ),
    }


def norwegian_workout_preview_line(ev: dict[str, Any]) -> str:
    day = str(ev.get("_day") or ev.get("start_date_local") or "")[:10]
    name = (ev.get("name") or "Økt").strip()
    sport = (ev.get("_sport") or ev.get("type") or "").strip()
    mins = ev.get("_duration_minutes")
    zwo = " · ZWO" if ev.get("_has_zwo") or ev.get("file_contents") else ""
    planned = ev.get("_planned") or ""
    planned_bit = f" · {Path(planned).stem}" if planned else ""
    dur = f"{mins} min" if mins else ""
    bits = [b for b in (day, name, sport, dur) if b]
    return " · ".join(bits) + zwo + planned_bit


def build_plan_sync_bundle(
    blocks: list[dict[str, Any]],
    *,
    athlete: dict[str, Any] | None = None,
    signals: dict[str, bool] | None = None,
    weeks: int = DEFAULT_WORKOUT_WEEKS,
    include_notes: bool = True,
    today: date | None = None,
    repo_root: Path | None = None,
    allow_degraded: bool = False,
    module_file: Path | None = None,
) -> dict[str, Any]:
    """NOTES (meso) + library WORKOUTs via CLI builder — one sync payload.

    When ``allow_degraded`` is True (setup Forhåndsvis), missing builder/workouts
    yields notes-only + ``error`` instead of raising — periodization must still
    render for restart and fresh onboarding.
    """
    signals = signals or signals_from_athlete(athlete)
    k_paths = knowledge_paths_for_workouts(athlete, signals)
    note_events = build_block_note_events(blocks) if include_notes else []
    try:
        workout_events = build_plan_week_icu_events(
            blocks,
            signals=signals,
            weeks=weeks,
            today=today,
            athlete=athlete,
            repo_root=repo_root,
            module_file=module_file,
        )
    except Exception as exc:
        if not allow_degraded:
            raise
        err_nb = format_exc_nb(exc)
        degraded = _notes_only_bundle(
            blocks,
            signals=signals,
            weeks=weeks,
            error=err_nb,
            athlete=athlete,
        )
        if not include_notes:
            degraded["note_events"] = []
            degraded["notes_count"] = 0
            degraded["notes_preview"] = []
            degraded["events"] = []
            degraded["events_preview"] = []
            degraded["count"] = 0
            degraded["description_no"] = (
                f"Øktbibliotek-forhåndsvisning feilet: {err_nb}"
            )
        return degraded
    workout_previews: list[dict[str, Any]] = []
    for ev in workout_events:
        row = public_event_preview(ev)
        row["sport"] = ev.get("_sport")
        row["duration_minutes"] = ev.get("_duration_minutes")
        row["planned"] = ev.get("_planned")
        row["has_zwo"] = bool(ev.get("_has_zwo"))
        row["filename"] = ev.get("filename")
        row["preview_no"] = norwegian_workout_preview_line(ev)
        workout_previews.append(row)

    note_previews = [public_event_preview(e) for e in note_events]
    all_events = list(note_events) + list(workout_events)
    zwo_n = sum(1 for e in workout_events if e.get("file_contents"))
    return {
        "events": all_events,
        "note_events": note_events,
        "workout_events": workout_events,
        "notes_count": len(note_events),
        "workouts_count": len(workout_events),
        "zwo_count": zwo_n,
        "count": len(all_events),
        "notes_preview": note_previews,
        "workouts_preview": workout_previews,
        "events_preview": note_previews + workout_previews,
        "signals": {k: v for k, v in signals.items() if not str(k).startswith("_")},
        "knowledge_paths": k_paths,
        "weeks": weeks,
        "builder": "scripts/intervals_push_calendar.build_workout_event",
        "kind": "calendar_notes_and_library_workouts",
        "error": None,
        "description_no": (
            f"Grovplan-noter ({len(note_events)}) + {len(workout_events)} økter "
            f"fra workouts/planned (første {weeks} uke(r), {zwo_n} med ZWO). "
            "Bygget med scripts/intervals_push_calendar.build_workout_event. "
            "Id: ll-coach-… / ll-coach-w-…. Upsert — andre ICU-hendelser urørt."
        ),
    }


def events_preview_for_plan_sync(
    blocks: list[dict[str, Any]],
    *,
    athlete: dict[str, Any] | None = None,
    signals: dict[str, bool] | None = None,
    weeks: int = DEFAULT_WORKOUT_WEEKS,
) -> dict[str, Any]:
    """Setup / Plan forhåndsvisning — never raises on missing workouts image."""
    prepared = []
    for i, b in enumerate(blocks):
        prepared.append({**b, "id": b.get("id") or f"draft-{b.get('key') or i}"})
    bundle = build_plan_sync_bundle(
        prepared,
        athlete=athlete,
        signals=signals,
        weeks=weeks,
        include_notes=True,
        allow_degraded=True,
    )
    out = {
        "will_push": False,
        "kind": bundle["kind"],
        "description": bundle["description_no"],
        "builder": bundle["builder"],
        "events_count": bundle["count"],
        "notes_count": bundle["notes_count"],
        "workouts_count": bundle["workouts_count"],
        "zwo_count": bundle["zwo_count"],
        "weeks": bundle["weeks"],
        "events_preview": bundle["events_preview"][:40],
        "workouts_preview": bundle["workouts_preview"][:40],
        "notes_preview": bundle["notes_preview"][:20],
        "events_truncated": max(0, bundle["count"] - 40),
        "signals": bundle["signals"],
        "knowledge_paths": bundle["knowledge_paths"],
    }
    if bundle.get("error"):
        out["error"] = bundle["error"]
        out["warning"] = bundle["description_no"]
    return out
