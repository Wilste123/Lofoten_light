"""Two-tier plan + roll-forward rules (Human Coach — never silent apply)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from two_tier_plan import (
    DETAIL_WEEKS,
    ROLL_COOLDOWN_DAYS,
    ROLL_TRIGGER_BLOCK_ELAPSED_DAYS,
    ROLL_TRIGGER_DAYS_LEFT,
    build_roll_proposal_card,
    build_two_tier_plan_payload,
    enrich_grov_blocks,
    evaluate_roll_trigger,
    user_requests_explicit_roll,
)


def test_constants_match_spec():
    assert DETAIL_WEEKS == 4
    assert ROLL_TRIGGER_DAYS_LEFT == 14
    assert ROLL_TRIGGER_BLOCK_ELAPSED_DAYS == 14
    assert ROLL_COOLDOWN_DAYS == 5


def test_explicit_roll_phrases():
    assert user_requests_explicit_roll("kan du planlegge neste måned?")
    assert user_requests_explicit_roll("rull videre")
    assert user_requests_explicit_roll("juster fremover")
    assert not user_requests_explicit_roll("hvordan går formen?")


def test_setup_payload_is_detalj_not_full_year():
    blocks = [
        {
            "id": "b0",
            "title": "Base",
            "theme": "aerob",
            "start_date": "2026-10-01",
            "end_date": "2027-01-01",
            "weekly_hours": 6,
        },
        {
            "id": "b1",
            "title": "Build",
            "theme": "bygg",
            "start_date": "2027-01-02",
            "end_date": "2027-08-20",
            "weekly_hours": 8,
        },
    ]
    athlete = {
        "goal_race_date": "2027-08-20",
        "sessions_per_week": 3,
        "allowed_disciplines": '["run","strength"]',
    }
    today = date(2026, 10, 1)
    payload = build_two_tier_plan_payload(blocks, athlete=athlete, today=today)
    assert payload["tier_model"] == "grov+detalj"
    assert payload["detalj_weeks"] == DETAIL_WEEKS
    assert payload["grov_horizon_weeks"] > DETAIL_WEEKS
    assert payload["count"] <= DETAIL_WEEKS * 4 + 2  # 3–4 sess/wk
    assert payload["count"] >= DETAIL_WEEKS  # at least ~one per week
    enriched = enrich_grov_blocks(blocks, athlete=athlete)
    assert enriched[0]["layer"] == "grov"
    assert "easy" in enriched[0]["session_types"]


def test_roll_trigger_days_left():
    today = date(2026, 10, 20)
    window = {
        "start_date": "2026-10-01",
        "end_date": "2026-10-28",  # 8 days left → ≤14
        "status": "active",
    }
    ev = evaluate_roll_trigger(
        today=today,
        plan_window=window,
        planned_sessions=[],
        plan_blocks=[],
        athlete={},
        message="",
    )
    assert ev["should_offer"] is True
    assert ev["trigger"] == "days_left"


def test_roll_cooldown_blocks_soft_offer():
    today = date(2026, 10, 20)
    window = {"start_date": "2026-10-01", "end_date": "2026-10-28", "status": "active"}
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    ev = evaluate_roll_trigger(
        today=today,
        plan_window=window,
        planned_sessions=[],
        plan_blocks=[],
        athlete={"detalj_roll_offered_at": recent},
        message="",
    )
    assert ev["in_cooldown"] is True
    assert ev["should_offer"] is False


def test_explicit_bypasses_cooldown():
    today = date(2026, 10, 20)
    window = {"start_date": "2026-10-01", "end_date": "2026-10-28", "status": "active"}
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    ev = evaluate_roll_trigger(
        today=today,
        plan_window=window,
        planned_sessions=[],
        plan_blocks=[{"id": "b0", "start_date": "2026-09-01", "end_date": "2026-12-01"}],
        athlete={"detalj_roll_offered_at": recent},
        message="planlegg neste måned",
    )
    assert ev["bypass_cooldown"] is True
    assert ev["should_offer"] is True
    assert ev["trigger"] == "explicit"


def test_block_elapsed_trigger():
    today = date(2026, 10, 20)
    blocks = [
        {
            "id": "b0",
            "title": "Base",
            "start_date": "2026-09-01",  # >14d elapsed
            "end_date": "2026-12-01",
        }
    ]
    # detalj only covers early October — not through block_start+28d
    sessions = [{"session_date": "2026-10-05", "name": "Easy"}]
    window = {"start_date": "2026-10-01", "end_date": "2027-10-01", "status": "active"}
    # end far away so days_left doesn't fire; block coverage missing
    window = {"start_date": "2026-10-01", "end_date": "2026-12-01", "status": "active"}
    # days left huge → only block trigger if coverage missing
    # block_start+28d = 2026-09-29 — sessions on 10-05 cover that, so should NOT trigger
    ev_covered = evaluate_roll_trigger(
        today=today,
        plan_window=window,
        planned_sessions=sessions,
        plan_blocks=blocks,
        athlete={},
        message="",
    )
    # 2026-10-05 >= 2026-09-29 → covered; days_left to 12-01 is large → no offer
    assert ev_covered["should_offer"] is False or ev_covered["trigger"] != "block_elapsed"

    sessions_short = [{"session_date": "2026-09-10", "name": "Easy"}]
    window_far = {"start_date": "2026-09-01", "end_date": "2026-12-01", "status": "active"}
    ev = evaluate_roll_trigger(
        today=today,
        plan_window=window_far,
        planned_sessions=sessions_short,
        plan_blocks=blocks,
        athlete={},
        message="",
    )
    assert ev["trigger"] == "block_elapsed"
    assert ev["should_offer"] is True


def test_roll_proposal_card_is_confirm_required():
    blocks = [
        {
            "id": "b0",
            "title": "Base",
            "start_date": "2026-10-01",
            "end_date": "2027-01-01",
            "weekly_hours": 5,
        }
    ]
    athlete = {"sessions_per_week": 3, "allowed_disciplines": '["run"]', "goal_race_date": "2027-08-20"}
    card = build_roll_proposal_card(
        blocks,
        athlete=athlete,
        next_start=date(2026, 10, 27),
        roll_eval={"trigger": "explicit", "reason": "test"},
    )
    assert card["op"] == "plan_roll"
    assert card["confirm_required"] is True
    assert card["detalj_weeks"] == DETAIL_WEEKS
    assert card["count"] == len(card["sessions"])
    assert "stille" in (card.get("message") or "").lower() or "bekreft" in (
        card.get("message") or ""
    ).lower()
