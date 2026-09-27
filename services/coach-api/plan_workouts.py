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
from athlete_constraints import (
    DISC_BIKE,
    DISC_RUN,
    DISC_STRENGTH,
    DISC_SWIM,
    MAX_WORKOUT_WEEKS,
    constraints_summary_nb,
    resolve_constraints,
    sport_to_discipline,
)
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


DEFAULT_WORKOUT_WEEKS = MAX_WORKOUT_WEEKS

# Session row: weekday 0=Mon … 6=Sun, then CSV fields for build_workout_event
# Optional trailing purpose_nb used for coach rationale (not pushed to ICU CSV).
SessionSpec = tuple  # (weekday, sport, subtype, title, duration_min, tss, planned_rel_path[, purpose_nb])
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
            "allowed_disciplines": athlete.get("allowed_disciplines") or "",
            "sessions_per_week": athlete.get("sessions_per_week") or "",
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
    constraints = resolve_constraints(athlete, athlete_type=atype)
    draft = {
        "goal_text": athlete.get("goal_text") or "",
        "injury_notes": athlete.get("injury_notes") or "",
        "schedule_notes": athlete.get("schedule_notes") or "",
        "background_notes": athlete.get("notes") or "",
        "notes": athlete.get("notes") or "",
        "athlete_type": atype or "",
        "sport": athlete.get("sport") or "",
        "allowed_disciplines": constraints["allowed_disciplines"],
        "sessions_per_week": constraints["sessions_per_week"],
    }
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
    n = constraints["sessions_per_week"]
    if n is not None and n <= 4:
        bits.append(f"{n} økter/uke lav frekvens")
    discs = constraints["allowed_disciplines"]
    if discs and (
        set(discs) == {DISC_RUN, DISC_STRENGTH}
        or discs == [DISC_RUN, DISC_STRENGTH]
    ):
        bits.append("kun løp og styrke")
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


def _spec(
    weekday: int,
    sport: str,
    subtype: str,
    title: str,
    duration: int,
    tss: int,
    planned: str,
    purpose_nb: str = "",
) -> SessionSpec:
    return (weekday, sport, subtype, title, duration, tss, planned, purpose_nb)


def _unpack_spec(spec: SessionSpec) -> tuple[int, str, str, str, int, int, str, str]:
    if len(spec) >= 8:
        return spec[0], spec[1], spec[2], spec[3], spec[4], spec[5], spec[6], spec[7]
    return spec[0], spec[1], spec[2], spec[3], spec[4], spec[5], spec[6], ""


def _filter_specs_by_disciplines(
    specs: list[SessionSpec], disciplines: list[str]
) -> list[SessionSpec]:
    allowed = set(disciplines or [])
    if not allowed:
        return specs
    out: list[SessionSpec] = []
    for spec in specs:
        disc = sport_to_discipline(spec[1])
        if disc and disc in allowed:
            out.append(spec)
    return out


def _cap_specs(specs: list[SessionSpec], n: int) -> list[SessionSpec]:
    """Keep ≤ n sessions; prefer spread weekdays and strength if agreed."""
    if n <= 0 or len(specs) <= n:
        return specs
    # Prefer: one strength (if any), longest run/bike, then earliest others
    strength = [s for s in specs if sport_to_discipline(s[1]) == DISC_STRENGTH]
    others = [s for s in specs if sport_to_discipline(s[1]) != DISC_STRENGTH]
    others_sorted = sorted(others, key=lambda s: (-int(s[4]), int(s[0])))
    picked: list[SessionSpec] = []
    if strength and n >= 2:
        picked.append(strength[0])
        remain = n - 1
    elif strength and n == 1:
        return [strength[0]]
    else:
        remain = n
    picked.extend(others_sorted[:remain])
    picked.sort(key=lambda s: int(s[0]))
    return picked


def _run_strength_low_freq_week(
    *,
    sessions: int,
    phase: str,
    weekly_hours: float,
    injury: bool,
    beginner: bool,
    athlete: dict[str, Any] | None,
) -> list[SessionSpec]:
    """Knowledge: lop/ukeplaner-lav-frekvens.md + styrke-og-lop.md + HM-periodisering."""
    inj_title, inj_path = injury_strength_session(athlete)
    strength = _spec(
        2,
        "Strength",
        "general",
        inj_title if injury else "Styrke base (ST01)",
        35,
        18 if injury else 20,
        inj_path if injury else "workouts/planned/strength/ST01-base.txt",
        "Skadefrihet / holdning midt i uka — ikke dagen før langtur",
    )
    easy = _spec(
        0,
        "Run",
        "recovery" if injury or beginner else "endurance",
        "Løp recovery 30 (R01)" if injury else "Løp easy 40 (R01)",
        30 if injury else 40,
        25 if injury else 40,
        (
            "workouts/planned/run/R01-recovery-30.txt"
            if injury
            else "workouts/planned/run/R01-easy-40.txt"
        ),
        "Kontinuitet · lav intensitet (80/20)",
    )
    long_run = (
        "workouts/planned/run/R04-long-easy-75.txt"
        if weekly_hours >= 6 and not injury and not beginner and phase not in ("etablering",)
        else "workouts/planned/run/R02-easy-55-strides.txt"
        if not injury
        else "workouts/planned/run/R01-easy-40.txt"
    )
    long_min = 75 if "R04" in long_run else (50 if "R02" in long_run else 40)
    long_tss = 70 if "R04" in long_run else (45 if "R02" in long_run else 40)
    long_title = (
        "Løp long easy 75 (R04)"
        if "R04" in long_run
        else (
            "Løp easy + strides (R02)"
            if "R02" in long_run
            else "Løp easy 40 (R01)"
        )
    )
    long_purpose = (
        "Aerob progresjon / langtur med restitusjon etterpå"
        if "R04" in long_run
        else "Aerob + nevromotorikk (strides) — ikke terskel"
    )
    long = _spec(5, "Run", "endurance", long_title, long_min, long_tss, long_run, long_purpose)

    if sessions <= 2:
        return [easy, strength]
    if sessions == 3:
        return [easy, strength, long]
    # 4: add mid-week easy trail or second easy (Tue), keep Thu free-ish
    mid = _spec(
        3,
        "Run",
        "endurance",
        "Løp trail/easy (R03)",
        55,
        50,
        "workouts/planned/run/R03-easy-trail-70.txt",
        "Ekstra aerob kontakt uten hard dag før helg",
    )
    if sessions >= 4:
        return [easy, strength, mid, long]
    return [easy, strength, long]


def _templates_for_signals(
    signals: dict[str, bool],
    *,
    phase: str,
    weekly_hours: float,
    athlete_type: str | None = None,
    athlete: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
) -> list[SessionSpec]:
    """Knowledge-aligned week from planned library (ukemaler / lav-frekvens).

    Paths are real ``workouts/planned/**`` files the CLI builder already resolves.
    Honours allowed_disciplines + sessions_per_week — never fills every day by default.
    """
    beginner = bool(signals.get("beginner"))
    injury = bool(signals.get("injury")) or phase == "rehab"
    time_c = bool(signals.get("time_constrained"))
    returning = bool(signals.get("returning"))
    atype = athlete_type or ""
    constraints = constraints or resolve_constraints(
        athlete, athlete_type=atype
    )
    discs = list(constraints.get("allowed_disciplines") or [])
    sessions_n = constraints.get("sessions_per_week")
    sessions_n = int(sessions_n) if sessions_n else 99
    run_primary = atype.endswith("runner") or atype == "runner"
    bike_primary = atype == "cyclist"
    swim_primary = atype == "swimmer"
    inj_title, inj_path = injury_strength_session(athlete)

    run_strength_only = set(discs) <= {DISC_RUN, DISC_STRENGTH} and DISC_RUN in discs
    if run_strength_only or (
        run_primary and DISC_SWIM not in discs and DISC_BIKE not in discs
    ):
        # Run+strength path always has a concrete weekly count
        sess = sessions_n if sessions_n < 90 else 4
        specs = _run_strength_low_freq_week(
            sessions=sess,
            phase=phase,
            weekly_hours=weekly_hours,
            injury=injury,
            beginner=beginner,
            athlete=athlete,
        )
        return _cap_specs(
            _filter_specs_by_disciplines(specs, discs or [DISC_RUN, DISC_STRENGTH]),
            sess,
        )

    # --- Bike-primary ---
    if bike_primary and not injury:
        specs = [
            _spec(0, "Bike", "recovery", "Sykkel recovery 45 (B01)", 45, 28,
                  "workouts/planned/bike/recovery-spin-45.txt", "Restitusjon / kontakt"),
            _spec(1, "Strength", "general", "Styrke base (ST01)", 35, 20,
                  "workouts/planned/strength/ST01-base.txt", "Styrke midtuke"),
            _spec(2, "Bike", "endurance", "Sykkel Z2 90 (B02)", 90, 55,
                  "workouts/planned/bike/endurance-90.txt", "Aerob Z2"),
            _spec(4, "Bike", "endurance", "Sykkel Z2 90 (B02)", 90, 55,
                  "workouts/planned/bike/endurance-90.txt", "Aerob Z2"),
            _spec(5, "Bike", "endurance", "Sykkel Z2 120 (B03)", 120, 75,
                  "workouts/planned/bike/endurance-120.txt", "Langtur sykkel"),
            _spec(6, "Run", "recovery", "Løp recovery 30 (R01)", 30, 25,
                  "workouts/planned/run/R01-recovery-30.txt", "Lett løpskontakt"),
        ]
        return _cap_specs(_filter_specs_by_disciplines(specs, discs), sessions_n)

    if swim_primary and not injury:
        specs = [
            _spec(0, "Swim", "technique", "Svøm teknikk A (S01)", 50, 35,
                  "workouts/planned/swim/S01-teknikk-a.txt", "Teknikk"),
            _spec(1, "Strength", "general", "Styrke base (ST01)", 35, 20,
                  "workouts/planned/strength/ST01-base.txt", "Styrke"),
            _spec(2, "Swim", "endurance", "Svøm aerob 3×500 (S03)", 55, 45,
                  "workouts/planned/swim/S03-aerob-3x500.txt", "Aerob svøm"),
            _spec(4, "Swim", "technique", "Svøm teknikk skulder (S02)", 40, 28,
                  "workouts/planned/swim/S02-teknikk-skulder.txt", "Skulder/teknikk"),
            _spec(5, "Swim", "endurance", "Svøm aerob 1500 (S04)", 55, 45,
                  "workouts/planned/swim/S04-aerob-1500.txt", "Kontinuerlig"),
            _spec(6, "Run", "recovery", "Løp recovery 30 (R01)", 30, 25,
                  "workouts/planned/run/R01-recovery-30.txt", "Lett løp"),
        ]
        return _cap_specs(_filter_specs_by_disciplines(specs, discs), sessions_n)

    # --- Injury / ACWR-safe ---
    if injury:
        if run_primary or run_strength_only:
            specs = [
                _spec(0, "Run", "recovery", "Løp recovery 30 (R01)", 30, 25,
                      "workouts/planned/run/R01-recovery-30.txt", "Lav impact kontinuitet"),
                _spec(2, "Strength", "general", inj_title, 35, 18, inj_path,
                      "Prehab / kontroll"),
                _spec(4, "Run", "endurance", "Løp easy 40 (R01)", 40, 40,
                      "workouts/planned/run/R01-easy-40.txt", "Easy volum"),
            ]
            # Optional bike only if allowed
            if DISC_BIKE in discs:
                specs.insert(
                    2,
                    _spec(3, "Bike", "recovery", "Sykkel recovery 45 (B01)", 45, 28,
                          "workouts/planned/bike/recovery-spin-45.txt", "Alternativ load"),
                )
            return _cap_specs(_filter_specs_by_disciplines(specs, discs), sessions_n)
        specs = [
            _spec(0, "Swim", "technique", "Svøm teknikk skulder (S02)", 40, 28,
                  "workouts/planned/swim/S02-teknikk-skulder.txt", "Lav impact"),
            _spec(1, "Bike", "recovery", "Sykkel recovery 45 (B01)", 45, 28,
                  "workouts/planned/bike/recovery-spin-45.txt", "Alternativ"),
            _spec(2, "Strength", "general", inj_title, 35, 18, inj_path, "Prehab"),
            _spec(4, "Swim", "recovery", "Svøm recovery (S09)", 35, 20,
                  "workouts/planned/swim/S09-recovery.txt", "Recovery"),
            _spec(5, "Bike", "endurance", "Sykkel Z2 90 (B02)", 90, 55,
                  "workouts/planned/bike/endurance-90.txt", "Aerob"),
            _spec(6, "Run", "recovery", "Løp recovery 30 (R01)", 30, 25,
                  "workouts/planned/run/R01-recovery-30.txt", "Lett løp"),
        ]
        return _cap_specs(_filter_specs_by_disciplines(specs, discs), sessions_n)

    # --- Beginner / time-constrained multi ---
    if beginner or (time_c and weekly_hours < 6):
        specs = [
            _spec(0, "Swim", "technique", "Svøm teknikk A (S01)", 50, 35,
                  "workouts/planned/swim/S01-teknikk-a.txt", "Teknikk-vane"),
            _spec(1, "Run", "endurance", "Løp easy 40 (R01)", 40, 40,
                  "workouts/planned/run/R01-easy-40.txt", "Easy løp"),
            _spec(2, "Bike", "recovery", "Sykkel recovery 45 (B01)", 45, 28,
                  "workouts/planned/bike/recovery-spin-45.txt", "Lett sykkel"),
            _spec(3, "Strength", "general", "Styrke base (ST01)", 35, 20,
                  "workouts/planned/strength/ST01-base.txt", "Styrke"),
            _spec(5, "Run", "endurance", "Løp easy + strides (R02)", 50, 45,
                  "workouts/planned/run/R02-easy-55-strides.txt", "Strides"),
        ]
        return _cap_specs(_filter_specs_by_disciplines(specs, discs), sessions_n)

    if time_c:
        specs = [
            _spec(0, "Swim", "technique", "Svøm teknikk A (S01)", 50, 35,
                  "workouts/planned/swim/S01-teknikk-a.txt", "Svøm"),
            _spec(1, "Run", "endurance", "Løp easy + strides (R02)", 50, 45,
                  "workouts/planned/run/R02-easy-55-strides.txt", "Løp"),
            _spec(2, "Bike", "endurance", "Sykkel Z2 90 (B02)", 90, 55,
                  "workouts/planned/bike/endurance-90.txt", "Sykkel Z2"),
            _spec(3, "Strength", "general", "Styrke base (ST01)", 35, 20,
                  "workouts/planned/strength/ST01-base.txt", "Styrke"),
            _spec(5, "Bike", "endurance", "Sykkel Z2 120 (B03)", 120, 75,
                  "workouts/planned/bike/endurance-120.txt", "Lengre sykkel"),
        ]
        return _cap_specs(_filter_specs_by_disciplines(specs, discs), sessions_n)

    # --- Returning / base tri (ukemaler Fase A) — only when multi disciplines ---
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
        specs = [
            _spec(0, "Swim", "technique", "Svøm teknikk A (S01)", 50, 35,
                  "workouts/planned/swim/S01-teknikk-a.txt", "Svøm-vane"),
            _spec(1, "Run", "endurance", "Løp easy 40 (R01)", 40, 40,
                  "workouts/planned/run/R01-easy-40.txt", "Løp easy"),
            _spec(2, "Bike", "endurance", "Sykkel Z2 90 (B02)", 90, 55,
                  "workouts/planned/bike/endurance-90.txt", "Sykkel Z2"),
            _spec(3, "Strength", "general", "Styrke base (ST01)", 35, 20,
                  "workouts/planned/strength/ST01-base.txt", "Styrke"),
            _spec(4, "Swim", "endurance", "Svøm aerob 3×500 (S03)", 55, 45,
                  "workouts/planned/swim/S03-aerob-3x500.txt", "Aerob svøm"),
            _spec(5, "Bike", "endurance", long_title, long_bike_min, long_bike_tss,
                  long_bike, "Langtur sykkel"),
            _spec(6, "Run", "endurance", "Løp easy + strides (R02)", 50, 45,
                  "workouts/planned/run/R02-easy-55-strides.txt", "Strides"),
        ]
        return _cap_specs(_filter_specs_by_disciplines(specs, discs), sessions_n)

    specs = [
        _spec(0, "Swim", "endurance", "Svøm aerob 1500 (S04)", 55, 45,
              "workouts/planned/swim/S04-aerob-1500.txt", "Svøm aerob"),
        _spec(1, "Run", "endurance", "Løp easy + strides (R02)", 50, 45,
              "workouts/planned/run/R02-easy-55-strides.txt", "Løp"),
        _spec(2, "Bike", "endurance", "Sykkel Z2 90 (B02)", 90, 55,
              "workouts/planned/bike/endurance-90.txt", "Sykkel"),
        _spec(3, "Strength", "general", "Styrke build (ST02)", 40, 22,
              "workouts/planned/strength/ST02-build.txt", "Styrke"),
        _spec(4, "Swim", "technique", "Svøm teknikk A (S01)", 50, 35,
              "workouts/planned/swim/S01-teknikk-a.txt", "Teknikk"),
        _spec(5, "Bike", "endurance", "Sykkel Z2 120 (B03)", 120, 75,
              "workouts/planned/bike/endurance-120.txt", "Lang sykkel"),
        _spec(6, "Run", "endurance", "Løp long easy 75 (R04)", 75, 70,
              "workouts/planned/run/R04-long-easy-75.txt", "Langtur løp"),
    ]
    return _cap_specs(_filter_specs_by_disciplines(specs, discs), sessions_n)


def build_prescription_rationale_nb(
    *,
    constraints: dict[str, Any],
    phase: str,
    signals: dict[str, bool],
    specs: list[SessionSpec],
    knowledge_paths: list[str],
) -> str:
    """Short Norwegian coach voice — why this week, not a random pack."""
    n = constraints.get("sessions_per_week") or len(specs)
    labels = constraints.get("disciplines_labels_no") or []
    disc = " + ".join(labels) if labels else "disipliner etter utøvertype"
    purposes = []
    for spec in specs:
        *_rest, purpose = _unpack_spec(spec)
        title = spec[3]
        if purpose:
            purposes.append(f"• {title}: {purpose}")
        else:
            purposes.append(f"• {title}")
    phase_bit = {
        "rehab": "skånsom / ACWR-trygg fase",
        "etablering": "etablering av vaner",
        "base": "aerob base",
        "build": "build med kontrollert kvalitet",
        "peak": "spesifikk oppbygging",
        "taper": "nedtrapping",
    }.get(phase, phase or "base")
    signal_bits = []
    if signals.get("beginner"):
        signal_bits.append("nybegynner — lav intensitet")
    if signals.get("returning"):
        signal_bits.append("comeback — ikke 2019-volum")
    if signals.get("injury"):
        signal_bits.append("skadehensyn")
    if signals.get("time_constrained") or (
        constraints.get("sessions_per_week")
        and int(constraints["sessions_per_week"]) <= 3
    ):
        signal_bits.append("få økter med luft mellom")
    sig_line = "; ".join(signal_bits) if signal_bits else "jevn progresjon"
    k_short = [
        p for p in knowledge_paths
        if p.startswith(("lop/", "coach/ukeplaner", "load-and-intensity", "skader/"))
    ][:5]
    k_line = ", ".join(k_short) if k_short else "coach/ukemaler + load-and-intensity"

    lines = [
        f"Ukesstruktur: {n} økter · {disc} · {phase_bit}.",
        f"Hvorfor: {sig_line}. Hviledager er bevisste — vi fyller ikke kalenderen.",
        "Økter:",
        *purposes,
        f"Knowledge: {k_line}.",
        "Kun første 2 uker pushes som WORKOUT til Intervals; grovplan dekker sesongen.",
    ]
    return "\n".join(lines)


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
    """Produce trainingdojo-compatible CSV rows for first ``weeks`` microcycles.

    Hard-capped at ``MAX_WORKOUT_WEEKS`` (2). Sessions honour athlete constraints.
    """
    if not blocks:
        return date.today(), []
    signals = signals or signals_from_athlete(athlete)
    atype = athlete_type_from_athlete(athlete)
    constraints = resolve_constraints(athlete, athlete_type=atype)
    weeks = max(1, min(int(weeks or DEFAULT_WORKOUT_WEEKS), MAX_WORKOUT_WEEKS))
    anchor = _anchor_start(blocks, today=today)
    if not anchor:
        return date.today(), []
    week0 = anchor - timedelta(days=anchor.weekday())
    rows: list[dict[str, str]] = []
    last_specs: list[SessionSpec] = []
    last_phase = "base"
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
            constraints=constraints,
        )
        last_specs = specs
        last_phase = phase
        for spec in specs:
            weekday, sport, subtype, title, dur, tss, planned, _purpose = _unpack_spec(
                spec
            )
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
    # Stash for bundle rationale (same process)
    build_plan_week_rows._last_meta = {  # type: ignore[attr-defined]
        "constraints": constraints,
        "specs": last_specs,
        "phase": last_phase,
        "weeks": weeks,
    }
    return week0, rows


def prescription_meta_from_athlete(
    athlete: dict[str, Any] | None,
    *,
    signals: dict[str, bool] | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Constraints + rationale for setup preview / plan sync."""
    signals = signals or signals_from_athlete(athlete)
    atype = athlete_type_from_athlete(athlete)
    constraints = resolve_constraints(athlete, athlete_type=atype)
    k_paths = knowledge_paths_for_workouts(athlete, signals)
    phase = "base"
    wh = 6.0
    if blocks:
        phase = _phase_of_block(blocks[0])
        try:
            wh = float(blocks[0].get("weekly_hours") or 6.0)
        except (TypeError, ValueError):
            wh = 6.0
    specs = _templates_for_signals(
        signals,
        phase=phase,
        weekly_hours=wh,
        athlete_type=atype,
        athlete=athlete,
        constraints=constraints,
    )
    rationale = build_prescription_rationale_nb(
        constraints=constraints,
        phase=phase,
        signals=signals,
        specs=specs,
        knowledge_paths=k_paths,
    )
    return {
        "constraints": constraints,
        "constraints_summary_nb": constraints_summary_nb(constraints),
        "prescription_rationale_nb": rationale,
        "knowledge_paths": k_paths,
        "sessions_this_week": len(specs),
        "max_workout_weeks": MAX_WORKOUT_WEEKS,
    }


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
    meta = prescription_meta_from_athlete(athlete, signals=signals, blocks=blocks)
    k_paths = meta["knowledge_paths"]
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
        "constraints": meta["constraints"],
        "constraints_summary_nb": meta["constraints_summary_nb"],
        "prescription_rationale_nb": meta["prescription_rationale_nb"],
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

    WORKOUT horizon hard-capped at 2 weeks. Disciplines/sessions from athlete
    agreements. When ``allow_degraded`` is True (setup Forhåndsvis), missing
    builder/workouts yields notes-only + ``error`` instead of raising.
    """
    weeks = max(1, min(int(weeks or DEFAULT_WORKOUT_WEEKS), MAX_WORKOUT_WEEKS))
    signals = signals or signals_from_athlete(athlete)
    meta = prescription_meta_from_athlete(athlete, signals=signals, blocks=blocks)
    k_paths = meta["knowledge_paths"]
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
    csum = meta["constraints_summary_nb"]
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
        "constraints": meta["constraints"],
        "constraints_summary_nb": csum,
        "prescription_rationale_nb": meta["prescription_rationale_nb"],
        "builder": "scripts/intervals_push_calendar.build_workout_event",
        "kind": "calendar_notes_and_library_workouts",
        "error": None,
        "description_no": (
            f"{csum}. Grovplan-noter ({len(note_events)}) + {len(workout_events)} økter "
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
    weeks = max(1, min(int(weeks or DEFAULT_WORKOUT_WEEKS), MAX_WORKOUT_WEEKS))
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
        "constraints": bundle.get("constraints"),
        "constraints_summary_nb": bundle.get("constraints_summary_nb"),
        "prescription_rationale_nb": bundle.get("prescription_rationale_nb"),
    }
    if bundle.get("error"):
        out["error"] = bundle["error"]
        out["warning"] = bundle["description_no"]
    return out
