"""Sunday ukesopp short-circuit — structured questions, no Intervals write."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat_service import (
    user_requests_ukesopp,
    ukesopp_prompt_payload,
    ukesopp_reply_nb,
)


def test_ukesopp_intent():
    assert user_requests_ukesopp("Kan vi ta ukesopp?")
    assert user_requests_ukesopp("hvordan gikk uka?")
    assert user_requests_ukesopp("weekly review please")
    assert not user_requests_ukesopp("sync til intervals")
    assert not user_requests_ukesopp("legg inn løp i morgen")
    assert not user_requests_ukesopp("sjekk uka mi")


def test_ukesopp_payload_and_reply():
    p = ukesopp_prompt_payload(
        week_start="2026-10-06",
        week_end="2026-10-12",
        planned_count=4,
    )
    assert len(p["questions"]) >= 4
    assert p["written_to_intervals"] is False
    assert p.get("can_save_answers") is True
    reply = ukesopp_reply_nb(
        name="William",
        week_start="2026-10-06",
        week_end="2026-10-12",
        planned_count=4,
        session_lines=["2026-10-07 · Rolig løp"],
    )
    assert "Ukesopp" in reply
    assert "Kontinuitet" in reply
    assert "Intervals-push" in reply or "push" in reply.lower()
    assert "lagres" in reply.lower() or "Lagre" in reply or "kortet" in reply.lower()
