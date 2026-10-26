"""Øktanalyse — one completed Intervals activity → coach feedback.

Fetches activity detail (+ intervals) and streams when available.
Read-only: never writes to Intervals. Soft-fails without credentials/streams.
"""

from __future__ import annotations

import statistics
import urllib.error
import urllib.parse
from datetime import date, datetime, timedelta
from typing import Any

from icu_http import http_get_json
from progress_compliance import API_BASE, _auth_headers, map_activity_type

# Streams we care about for graphs / signing
_STREAM_TYPES = "watts,heartrate,cadence,time,velocity_smooth"
# Downsample cap for UI polyline (keep useful shape without huge payloads)
_MAX_SERIES_POINTS = 180


def _float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _int(val: Any) -> int | None:
    f = _float(val)
    if f is None:
        return None
    return int(round(f))


def resolve_activity_id(session_or_id: str | dict[str, Any] | None) -> str | None:
    """Extract bare ICU activity id from ``act:123`` / session dict / raw id."""
    if session_or_id is None:
        return None
    if isinstance(session_or_id, dict):
        kind = (session_or_id.get("kind") or "").lower()
        ext = str(session_or_id.get("external_id") or "").strip()
        sid = str(session_or_id.get("id") or "").strip()
        if kind == "activity" and ext:
            return ext
        if sid.startswith("act:"):
            return sid.split(":", 1)[1].strip() or None
        # Matched planned event → linked activity
        matched = session_or_id.get("matched_activity_id") or session_or_id.get(
            "activity_id"
        )
        if matched:
            return resolve_activity_id(str(matched))
        if ext and not sid.startswith("evt:"):
            # Might already be bare ICU id on activity rows
            if kind in ("activity", "completed_activity", ""):
                return ext
        return None
    text = str(session_or_id).strip()
    if not text:
        return None
    if text.startswith("act:"):
        return text.split(":", 1)[1].strip() or None
    if text.startswith("evt:"):
        return None
    return text


def fetch_activity_detail(
    api_key: str,
    activity_id: str,
    *,
    intervals: bool = True,
    timeout: int = 20,
) -> dict[str, Any] | None:
    """GET /activity/{id}?intervals=true — soft None on failure."""
    key = (api_key or "").strip()
    aid = (activity_id or "").strip()
    if not key or not aid:
        return None
    qs = "intervals=true" if intervals else ""
    url = f"{API_BASE}/activity/{urllib.parse.quote(aid)}"
    if qs:
        url = f"{url}?{qs}"
    try:
        data = http_get_json(url, _auth_headers(key), timeout=timeout)
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        ValueError,
        OSError,
    ):
        return None
    return data if isinstance(data, dict) else None


def fetch_activity_streams(
    api_key: str,
    activity_id: str,
    *,
    types: str = _STREAM_TYPES,
    timeout: int = 25,
) -> list[dict[str, Any]]:
    """GET /activity/{id}/streams.json?types=… — empty list on failure."""
    key = (api_key or "").strip()
    aid = (activity_id or "").strip()
    if not key or not aid:
        return []
    qs = urllib.parse.urlencode({"types": types})
    url = f"{API_BASE}/activity/{urllib.parse.quote(aid)}/streams.json?{qs}"
    try:
        data = http_get_json(url, _auth_headers(key), timeout=timeout)
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        ValueError,
        OSError,
    ):
        return []
    if isinstance(data, dict):
        # Some shapes wrap streams
        for k in ("streams", "data", "list"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
        else:
            # dict of type → data
            out = []
            for t, series in data.items():
                if isinstance(series, list):
                    out.append({"type": t, "data": series})
                elif isinstance(series, dict) and isinstance(series.get("data"), list):
                    out.append({"type": t, "data": series["data"]})
            return out
    if not isinstance(data, list):
        return []
    return [s for s in data if isinstance(s, dict)]


def streams_to_map(streams: list[dict[str, Any]]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for s in streams or []:
        t = str(s.get("type") or s.get("stream_type") or "").strip().lower()
        data = s.get("data")
        if t and isinstance(data, list) and data:
            out[t] = data
    return out


def downsample_series(
    values: list[Any],
    *,
    max_points: int = _MAX_SERIES_POINTS,
) -> list[float | None]:
    """Evenly downsample numeric series; preserve None gaps."""
    n = len(values)
    if n <= max_points:
        result: list[float | None] = []
        for v in values:
            if v is None:
                result.append(None)
            else:
                try:
                    result.append(round(float(v), 2))
                except (TypeError, ValueError):
                    result.append(None)
        return result
    step = n / max_points
    out: list[float | None] = []
    for i in range(max_points):
        idx = min(n - 1, int(i * step))
        v = values[idx]
        if v is None:
            out.append(None)
        else:
            try:
                out.append(round(float(v), 2))
            except (TypeError, ValueError):
                out.append(None)
    return out


def build_graph_series(stream_map: dict[str, list[Any]]) -> dict[str, Any]:
    """Downsampled HR/power/time for UI SVG — structured summary if empty."""
    watts = stream_map.get("watts") or []
    hr = stream_map.get("heartrate") or []
    time_s = stream_map.get("time") or []
    n = max(len(watts), len(hr), len(time_s))
    if n == 0:
        return {
            "available": False,
            "points": 0,
            "note_nb": "Ingen streams (watt/puls) tilgjengelig for denne økten.",
        }
    # Build time axis if missing (assume 1 Hz)
    if not time_s:
        time_s = list(range(n))
    # Align lengths
    def _pad(seq: list[Any], length: int) -> list[Any]:
        if len(seq) >= length:
            return seq[:length]
        return list(seq) + [None] * (length - len(seq))

    length = min(len(time_s), max(len(watts) or 0, len(hr) or 0, len(time_s)))
    if length < 2:
        return {
            "available": False,
            "points": length,
            "note_nb": "For få stream-punkter til graf.",
        }
    time_s = _pad(time_s, length)
    watts = _pad(watts, length) if watts else []
    hr = _pad(hr, length) if hr else []

    t_ds = downsample_series(time_s)
    w_ds = downsample_series(watts) if watts else []
    h_ds = downsample_series(hr) if hr else []
    # Re-align after downsample to shared index count
    m = max(len(t_ds), len(w_ds), len(h_ds))
    points: list[dict[str, Any]] = []
    for i in range(min(m, _MAX_SERIES_POINTS)):
        pt: dict[str, Any] = {
            "t": t_ds[i] if i < len(t_ds) else None,
        }
        if w_ds and i < len(w_ds):
            pt["watts"] = w_ds[i]
        if h_ds and i < len(h_ds):
            pt["hr"] = h_ds[i]
        points.append(pt)
    return {
        "available": True,
        "points": len(points),
        "has_watts": bool(w_ds and any(v is not None for v in w_ds)),
        "has_hr": bool(h_ds and any(v is not None for v in h_ds)),
        "series": points,
        "note_nb": None,
    }


def extract_icu_intervals(activity: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not activity:
        return []
    raw = (
        activity.get("icu_intervals")
        or activity.get("intervals")
        or (activity.get("icu") or {}).get("intervals")
    )
    if isinstance(raw, dict):
        raw = raw.get("icu_intervals") or raw.get("intervals") or raw.get("list")
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def _interval_is_work(iv: dict[str, Any]) -> bool:
    """Heuristic: WORK / ACTIVE / high IF, skip rests and warmups when flagged."""
    typ = str(iv.get("type") or iv.get("group") or iv.get("label") or "").upper()
    if typ in ("REST", "RECOVERY", "COOLDOWN", "WARMUP", "WU", "CD"):
        return False
    if iv.get("is_rest") is True or iv.get("rest") is True:
        return False
    # Distance/time work pieces usually have moving_time and load/intensity
    return True


def analyze_intervals(
    intervals: list[dict[str, Any]],
    *,
    sport: str | None = None,
) -> dict[str, Any]:
    """Consistency + target hit rate from ICU interval laps."""
    work = [iv for iv in intervals if _interval_is_work(iv)]
    if not work:
        return {
            "available": False,
            "count": 0,
            "note_nb": "Ingen intervall-laps i Intervals for denne økten.",
            "laps": [],
            "verdict_nb": None,
        }

    laps: list[dict[str, Any]] = []
    powers: list[float] = []
    hrs: list[float] = []
    durs: list[float] = []
    for i, iv in enumerate(work[:40], start=1):
        dur = (
            _float(iv.get("moving_time"))
            or _float(iv.get("elapsed_time"))
            or _float(iv.get("duration"))
            or _float(iv.get("seconds"))
        )
        avg_w = (
            _float(iv.get("average_watts"))
            or _float(iv.get("avg_watts"))
            or _float(iv.get("watts"))
            or _float(iv.get("icu_average_watts"))
        )
        avg_hr = (
            _float(iv.get("average_heartrate"))
            or _float(iv.get("avg_hr"))
            or _float(iv.get("hr"))
            or _float(iv.get("average_hr"))
        )
        target_w = (
            _float(iv.get("target_watts"))
            or _float(iv.get("start_watts"))
            or _float(iv.get("end_watts"))
        )
        # Some ICU intervals use power zone % fields
        inten = _float(iv.get("intensity")) or _float(iv.get("icu_intensity"))
        pace = _float(iv.get("average_speed")) or _float(iv.get("pace"))
        lap = {
            "n": i,
            "duration_s": int(dur) if dur is not None else None,
            "avg_watts": round(avg_w, 0) if avg_w is not None else None,
            "avg_hr": round(avg_hr, 0) if avg_hr is not None else None,
            "target_watts": round(target_w, 0) if target_w is not None else None,
            "intensity": round(inten, 3) if inten is not None else None,
            "pace_or_speed": round(pace, 3) if pace is not None else None,
            "name": str(iv.get("name") or iv.get("label") or f"Drag {i}")[:80],
        }
        if avg_w is not None and target_w is not None and target_w > 0:
            lap["vs_target_pct"] = round(100.0 * avg_w / target_w, 1)
        laps.append(lap)
        if avg_w is not None and avg_w > 0:
            powers.append(avg_w)
        if avg_hr is not None and avg_hr > 0:
            hrs.append(avg_hr)
        if dur is not None and dur > 0:
            durs.append(dur)

    def _cv(vals: list[float]) -> float | None:
        if len(vals) < 2:
            return None
        mean = statistics.mean(vals)
        if mean <= 0:
            return None
        return round(100.0 * statistics.pstdev(vals) / mean, 1)

    power_cv = _cv(powers)
    hr_cv = _cv(hrs)
    dur_cv = _cv(durs)

    verdict_parts: list[str] = []
    if power_cv is not None:
        if power_cv <= 4:
            verdict_parts.append(f"Watt-konsistens bra (CV {power_cv} %).")
        elif power_cv <= 8:
            verdict_parts.append(
                f"Watt spredning OK (CV {power_cv} %) — litt mer jevnhet i dragene."
            )
        else:
            verdict_parts.append(
                f"Watt for ujevnt (CV {power_cv} %) — første/siste drag skiller seg."
            )
    if hr_cv is not None and power_cv is None:
        if hr_cv <= 3:
            verdict_parts.append(f"Puls jevn (CV {hr_cv} %).")
        else:
            verdict_parts.append(f"Puls spredt (CV {hr_cv} %) — sjekk pacing.")
    if dur_cv is not None and dur_cv > 12:
        verdict_parts.append(
            f"Varighet på dragene varierer (CV {dur_cv} %) — hold strukturen."
        )

    vs_targets = [lap["vs_target_pct"] for lap in laps if lap.get("vs_target_pct") is not None]
    if vs_targets:
        avg_vs = statistics.mean(vs_targets)
        if 95 <= avg_vs <= 105:
            verdict_parts.append(f"Traff mål (~{avg_vs:.0f} % av target).")
        elif avg_vs > 105:
            verdict_parts.append(
                f"Overshoot (~{avg_vs:.0f} % av target) — ro deg ned, ikke sprint."
            )
        else:
            verdict_parts.append(
                f"Under target (~{avg_vs:.0f} %) — enten for hardt satt, eller for forsiktig."
            )

    if not verdict_parts:
        verdict_parts.append(
            f"{len(laps)} drag logget — begrenset mål-data; vurder følelse/RPE selv."
        )

    return {
        "available": True,
        "count": len(laps),
        "sport": sport,
        "power_cv_pct": power_cv,
        "hr_cv_pct": hr_cv,
        "duration_cv_pct": dur_cv,
        "avg_watts": round(statistics.mean(powers), 0) if powers else None,
        "avg_hr": round(statistics.mean(hrs), 0) if hrs else None,
        "laps": laps,
        "verdict_nb": " ".join(verdict_parts),
        "note_nb": None,
    }


def intensity_distribution(
    activity: dict[str, Any] | None,
    stream_map: dict[str, list[Any]],
    *,
    ftp: float | None = None,
    lthr: float | None = None,
) -> dict[str, Any]:
    """Signing / intensity distribution from ICU fields or stream buckets."""
    act = activity or {}
    # Prefer ICU zone times if present (seconds per zone)
    zone_keys = (
        "icu_zone_times",
        "zone_times",
        "icu_hr_zone_times",
        "hr_zone_times",
        "icu_power_zone_times",
    )
    for zk in zone_keys:
        zt = act.get(zk)
        if isinstance(zt, list) and zt:
            labels = [f"Z{i}" for i in range(1, len(zt) + 1)]
            secs = [_float(x) or 0.0 for x in zt]
            total = sum(secs) or 1.0
            zones = [
                {
                    "zone": labels[i],
                    "seconds": int(secs[i]),
                    "pct": round(100.0 * secs[i] / total, 1),
                }
                for i in range(len(secs))
                if secs[i] > 0
            ]
            return {
                "available": True,
                "source": zk,
                "zones": zones,
                "easy_pct": _easy_share(zones),
                "hard_pct": _hard_share(zones),
                "note_nb": None,
            }

    # Stream-based rough buckets
    watts = [ _float(v) for v in (stream_map.get("watts") or []) ]
    watts = [v for v in watts if v is not None and v > 0]
    hr = [ _float(v) for v in (stream_map.get("heartrate") or []) ]
    hr = [v for v in hr if v is not None and v > 0]

    if watts and ftp and ftp > 50:
        buckets = {
            "Z1 (<55%)": 0,
            "Z2 (55–75%)": 0,
            "Z3 (75–90%)": 0,
            "Z4 (90–105%)": 0,
            "Z5+ (>105%)": 0,
        }
        for w in watts:
            pct = 100.0 * w / ftp
            if pct < 55:
                buckets["Z1 (<55%)"] += 1
            elif pct < 75:
                buckets["Z2 (55–75%)"] += 1
            elif pct < 90:
                buckets["Z3 (75–90%)"] += 1
            elif pct < 105:
                buckets["Z4 (90–105%)"] += 1
            else:
                buckets["Z5+ (>105%)"] += 1
        total = sum(buckets.values()) or 1
        zones = [
            {"zone": k, "seconds": v, "pct": round(100.0 * v / total, 1)}
            for k, v in buckets.items()
            if v > 0
        ]
        return {
            "available": True,
            "source": "watts_vs_ftp",
            "ftp_used": ftp,
            "zones": zones,
            "easy_pct": round(
                100.0
                * (buckets["Z1 (<55%)"] + buckets["Z2 (55–75%)"])
                / total,
                1,
            ),
            "hard_pct": round(
                100.0
                * (buckets["Z4 (90–105%)"] + buckets["Z5+ (>105%)"])
                / total,
                1,
            ),
            "note_nb": "Estimert fra watt-stream vs FTP (ikke ICU-soner).",
        }

    if hr and lthr and lthr > 80:
        buckets = {"Z1–2": 0, "Z3": 0, "Z4+": 0}
        for h in hr:
            pct = 100.0 * h / lthr
            if pct < 85:
                buckets["Z1–2"] += 1
            elif pct < 95:
                buckets["Z3"] += 1
            else:
                buckets["Z4+"] += 1
        total = sum(buckets.values()) or 1
        zones = [
            {"zone": k, "seconds": v, "pct": round(100.0 * v / total, 1)}
            for k, v in buckets.items()
            if v > 0
        ]
        return {
            "available": True,
            "source": "hr_vs_lthr",
            "lthr_used": lthr,
            "zones": zones,
            "easy_pct": round(100.0 * buckets["Z1–2"] / total, 1),
            "hard_pct": round(100.0 * buckets["Z4+"] / total, 1),
            "note_nb": "Estimert fra puls-stream vs LTHR.",
        }

    # Fallback: single IF / intensity from activity summary
    inten = (
        _float(act.get("icu_intensity"))
        or _float(act.get("intensity"))
        or _float(act.get("icu_intensity_factor"))
    )
    if inten is not None:
        if inten > 3:
            inten = inten / 100.0
        return {
            "available": True,
            "source": "icu_intensity",
            "intensity_factor": round(inten, 3),
            "zones": [],
            "easy_pct": None,
            "hard_pct": None,
            "note_nb": (
                f"IF/intensitet ~{inten:.2f} — ingen sonefordeling i streams."
            ),
        }

    return {
        "available": False,
        "zones": [],
        "note_nb": "Ingen sone-/intensitetsdata for signing.",
    }


def _easy_share(zones: list[dict[str, Any]]) -> float | None:
    easy_labels = {"Z1", "Z2", "Z1–2", "Z1 (<55%)", "Z2 (55–75%)"}
    total = sum(float(z.get("pct") or 0) for z in zones) or 0
    if total <= 0:
        return None
    easy = sum(
        float(z.get("pct") or 0)
        for z in zones
        if str(z.get("zone") or "") in easy_labels
        or str(z.get("zone") or "").startswith("Z1")
        or str(z.get("zone") or "").startswith("Z2")
    )
    return round(easy, 1)


def _hard_share(zones: list[dict[str, Any]]) -> float | None:
    hard = sum(
        float(z.get("pct") or 0)
        for z in zones
        if str(z.get("zone") or "").startswith("Z4")
        or str(z.get("zone") or "").startswith("Z5")
        or "Z4+" in str(z.get("zone") or "")
    )
    return round(hard, 1) if hard else 0.0


def activity_summary(activity: dict[str, Any] | None) -> dict[str, Any]:
    act = activity or {}
    sport = map_activity_type(act.get("type") or act.get("sport"))
    dur = (
        _float(act.get("moving_time"))
        or _float(act.get("elapsed_time"))
        or _float(act.get("duration"))
    )
    load = (
        _float(act.get("icu_training_load"))
        or _float(act.get("training_load"))
        or _float(act.get("icu_tss"))
        or _float(act.get("tss"))
    )
    inten = _float(act.get("icu_intensity")) or _float(act.get("intensity"))
    if inten is not None and inten > 3:
        inten = inten / 100.0
    start = act.get("start_date_local") or act.get("start_date") or act.get("date")
    date_s = None
    if start:
        try:
            text = str(start)
            date_s = (
                datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
                if "T" in text
                else text[:10]
            )
        except ValueError:
            date_s = str(start)[:10]
    return {
        "id": str(act.get("id") or ""),
        "name": str(act.get("name") or act.get("type") or "Økt"),
        "sport": sport,
        "sport_raw": act.get("type") or act.get("sport"),
        "date": date_s,
        "duration_s": int(dur) if dur is not None else None,
        "duration_min": round(dur / 60.0, 1) if dur is not None else None,
        "load": round(load, 0) if load is not None else None,
        "intensity": round(inten, 3) if inten is not None else None,
        "avg_watts": _int(
            act.get("icu_weighted_avg_watts")
            or act.get("icu_average_watts")
            or act.get("average_watts")
            or act.get("weighted_average_watts")
        ),
        "avg_hr": _int(
            act.get("average_heartrate")
            or act.get("avg_hr")
            or act.get("icu_average_hr")
        ),
        "max_hr": _int(act.get("max_heartrate") or act.get("max_hr")),
        "distance_m": _float(act.get("distance")),
        "stream_types": act.get("stream_types") or [],
    }


def opv_feedback_nb(
    *,
    summary: dict[str, Any],
    intervals: dict[str, Any],
    distribution: dict[str, Any],
    graph: dict[str, Any],
) -> str:
    """Honest Norwegian OPV-style session comment — not fluff."""
    name = summary.get("name") or "Økt"
    lines: list[str] = [f"[{name}]"]
    bits: list[str] = []
    if summary.get("duration_min") is not None:
        bits.append(f"{summary['duration_min']:.0f} min")
    if summary.get("load") is not None:
        bits.append(f"load {int(summary['load'])}")
    if summary.get("intensity") is not None:
        bits.append(f"IF {summary['intensity']:.2f}")
    if summary.get("avg_watts") is not None:
        bits.append(f"snitt {summary['avg_watts']} W")
    if summary.get("avg_hr") is not None:
        bits.append(f"puls {summary['avg_hr']}")
    if bits:
        lines.append("Tall: " + " · ".join(bits) + ".")

    if intervals.get("available") and intervals.get("verdict_nb"):
        lines.append(f"Struktur: {intervals['verdict_nb']}")
    elif not intervals.get("available"):
        lines.append(
            "Struktur: Ingen tydelige intervall-laps — "
            "enten jevn økt, eller Intervals har ikke merket dragene."
        )

    if distribution.get("available"):
        easy = distribution.get("easy_pct")
        hard = distribution.get("hard_pct")
        if easy is not None and hard is not None:
            lines.append(
                f"Signing: ~{easy:.0f} % rolig / ~{hard:.0f} % hardt "
                f"({distribution.get('source') or 'soner'})."
            )
            if hard is not None and hard > 35 and (summary.get("intensity") or 0) > 0.85:
                lines.append(
                    "Pass på: høy hard-andel — ikke «ta igjen» i neste rolige økt."
                )
            elif easy is not None and easy >= 70:
                lines.append("Bra: mesteparten i rolig — det er stødig base.")
        elif distribution.get("note_nb"):
            lines.append(f"Signing: {distribution['note_nb']}")
        elif distribution.get("intensity_factor") is not None:
            lines.append(
                f"Signing: IF {distribution['intensity_factor']:.2f} "
                "(uten sonefordeling)."
            )
    else:
        lines.append("Signing: mangler sone-/stream-data — vurder RPE ærlig.")

    if not graph.get("available"):
        lines.append(
            "Graf: ingen watt/puls-stream — oppsummering fra aktivitetsfelter."
        )

    # Closing OPV nudge
    sport = summary.get("sport") or ""
    if sport == "swim":
        lines.append(
            "Svøm er limiteren: én teknikk-ting å ta med neste økt — ikke bare meter."
        )
    elif sport == "bike":
        lines.append(
            "Neste: hold neste langtur/Z2 faktisk rolig. Ikke jakt watt fordi denne økta gikk bra."
        )
    elif sport == "run":
        lines.append(
            "Neste: terreng/underlag først — ikke øk fart før kontinuiteten sitter."
        )
    else:
        lines.append("Neste: én ting å skjerpe — ikke tre.")

    return "\n".join(lines)


def analyze_activity_payload(
    *,
    activity: dict[str, Any] | None,
    streams: list[dict[str, Any]] | None = None,
    ftp: float | None = None,
    lthr: float | None = None,
) -> dict[str, Any]:
    """Pure analysis from already-fetched ICU payloads (testable offline)."""
    summary = activity_summary(activity)
    stream_map = streams_to_map(streams or [])
    graph = build_graph_series(stream_map)
    iv_raw = extract_icu_intervals(activity)
    intervals = analyze_intervals(iv_raw, sport=summary.get("sport"))
    distribution = intensity_distribution(
        activity, stream_map, ftp=ftp, lthr=lthr
    )
    feedback = opv_feedback_nb(
        summary=summary,
        intervals=intervals,
        distribution=distribution,
        graph=graph,
    )
    return {
        "available": bool(activity),
        "summary": summary,
        "graph": graph,
        "intervals": intervals,
        "distribution": distribution,
        "feedback_nb": feedback,
        "written_to_intervals": False,
        "source": "intervals.icu",
    }


def pick_latest_activity_session(
    bundle: dict[str, Any] | None,
    *,
    prefer_date: str | None = None,
) -> dict[str, Any] | None:
    """Choose newest completed ICU activity from sessions bundle."""
    rows: list[dict[str, Any]] = []
    for key in ("completed", "recent", "today"):
        for s in (bundle or {}).get(key) or []:
            if not isinstance(s, dict):
                continue
            if s.get("kind") == "activity" or str(s.get("id") or "").startswith("act:"):
                rows.append(s)
    if not rows:
        return None
    if prefer_date:
        same = [s for s in rows if str(s.get("date") or "")[:10] == prefer_date[:10]]
        if same:
            rows = same
    rows.sort(
        key=lambda s: str(
            s.get("start_date_local") or s.get("date") or ""
        ),
        reverse=True,
    )
    return rows[0]


def analyze_session_for_athlete(
    secrets: dict[str, Any] | None,
    *,
    session_id: str | None = None,
    session: dict[str, Any] | None = None,
    bundle: dict[str, Any] | None = None,
    ftp: float | None = None,
    lthr: float | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """End-to-end: resolve activity → fetch detail/streams → analyse.

    Soft empty when Intervals missing or session is not an activity.
    """
    today = today or date.today()
    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    if not key:
        return {
            "available": False,
            "note": "Intervals ikke koblet — kan ikke hente øktstreams.",
            "written_to_intervals": False,
            "feedback_nb": "Koble Intervals under Du før øktanalyse.",
        }

    sess = session
    if sess is None and session_id and bundle:
        from sessions_service import find_session_in_bundle

        sess = find_session_in_bundle(bundle, session_id)
    if sess is None and not session_id and bundle:
        sess = pick_latest_activity_session(
            bundle, prefer_date=today.isoformat()
        )
        if sess is None:
            # Fall back to most recent any day
            sess = pick_latest_activity_session(bundle)

    aid = resolve_activity_id(sess) if sess else resolve_activity_id(session_id)
    if not aid:
        # Maybe session_id is bare / act:
        aid = resolve_activity_id(session_id)
    if not aid:
        return {
            "available": False,
            "note": "Ingen gjennomført ICU-aktivitet å analysere (velg en økt under Økter).",
            "written_to_intervals": False,
            "feedback_nb": (
                "Fant ingen logget aktivitet. Åpne en gjennomført økt "
                "eller si «analyser dagens økt» etter at filen er i Intervals."
            ),
            "session_id": session_id,
        }

    detail = fetch_activity_detail(key, aid, intervals=True)
    if not detail:
        return {
            "available": False,
            "note": f"Kunne ikke hente aktivitet {aid} fra Intervals.",
            "activity_id": aid,
            "written_to_intervals": False,
            "feedback_nb": "Intervals svarte ikke på aktivitetsdetalj — prøv igjen.",
        }

    streams = fetch_activity_streams(key, aid)
    result = analyze_activity_payload(
        activity=detail,
        streams=streams,
        ftp=ftp,
        lthr=lthr,
    )
    result["activity_id"] = aid
    result["session_id"] = (
        str(sess.get("id")) if isinstance(sess, dict) and sess.get("id") else f"act:{aid}"
    )
    result["streams_fetched"] = bool(streams)
    result["written_to_intervals"] = False
    if not result.get("available"):
        result["note"] = result.get("note") or "Analyse utilgjengelig."
    return result


def session_analysis_reply_nb(
    *,
    name: str,
    analysis: dict[str, Any],
) -> str:
    """Short coach chat reply wrapping feedback."""
    if not analysis.get("available"):
        note = analysis.get("note") or analysis.get("feedback_nb") or "Ingen analyse."
        return f"{name.split()[0] if name else 'Ok'}: {note}"
    summary = analysis.get("summary") or {}
    head = summary.get("name") or "Økt"
    day = summary.get("date") or ""
    body = analysis.get("feedback_nb") or ""
    return (
        f"Øktanalyse — {head}"
        + (f" ({day})" if day else "")
        + ":\n\n"
        + body
        + "\n\n*(Les-only — ingen sync til Intervals.)*"
    )
