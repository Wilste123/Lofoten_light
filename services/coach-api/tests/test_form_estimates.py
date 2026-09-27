"""Tests for form_estimates gate and MMP FTP."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from form_estimates import (
    ActivityPower,
    MIN_QUALIFYING_SESSIONS,
    compute_form_estimates,
    count_qualifying_sessions,
    estimate_ftp_from_mmp,
    gate_open,
)


def _bike(duration: float = 45, power: float = 180, mmp: dict | None = None) -> ActivityPower:
    return ActivityPower(
        duration_min=duration,
        mean_power=power,
        mmp=mmp or {20: power},
        has_power=True,
    )


def test_gate_closed_under_five():
    acts = [_bike() for _ in range(4)]
    assert count_qualifying_sessions(acts) == 4
    assert not gate_open(acts)
    r = compute_form_estimates(acts)
    assert r["gate_open"] is False
    assert r["ftp_estimated"] is None
    assert "5 sykkeløkter" in (r["disclaimer"] or "")


def test_gate_open_at_five():
    acts = [
        _bike(mmp={20: 200}),
        _bike(mmp={20: 210}),
        _bike(mmp={12: 220}),
        _bike(mmp={8: 230}),
        _bike(mmp={20: 205}),
    ]
    assert count_qualifying_sessions(acts) == MIN_QUALIFYING_SESSIONS
    assert gate_open(acts)
    r = compute_form_estimates(acts)
    assert r["gate_open"] is True
    assert r["ftp_estimated"] is not None
    # aggregate max MMP then factors: 20→210*0.95=199.5, 12→198, 8→202.4 → min = 198
    assert r["ftp_estimated"] == 198.0
    assert r["estimate_confidence"] == "medium"


def test_short_session_not_qualifying():
    acts = [_bike(duration=15) for _ in range(5)]
    assert count_qualifying_sessions(acts) == 0
    assert not gate_open(acts)


def test_no_power_not_qualifying():
    acts = [
        ActivityPower(duration_min=60, mean_power=None, mmp=None, has_power=False)
        for _ in range(5)
    ]
    assert not gate_open(acts)


def test_ftp_cap_vs_tested():
    mmp = {5: 400}  # only short → low confidence, high raw
    # With only 5 min: P*0.85 = 340; tested 200 → should cap
    out = estimate_ftp_from_mmp(mmp, ftp_tested=200)
    assert out["capped"] is True
    assert out["ftp_estimated"] == 210.0  # 200 * 1.05
    assert out["confidence"] == "lav"


def test_prefer_longer_windows_min():
    # 20 min candidate lower than 8 min — pick min of ≥8
    mmp = {20: 200, 8: 280}
    out = estimate_ftp_from_mmp(mmp)
    assert out["ftp_estimated"] == 190.0  # 200*0.95
    assert out["confidence"] == "høy"
