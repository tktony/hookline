"""Tests for request/response schemas."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models import DeliveryAttempt, Event
from app.schemas import EventDetailOut, EventOut, WebhookIn


def test_accepts_normal_payload():
    """A small payload validates fine."""
    w = WebhookIn(target_url="https://example.com/hook", payload={"event": "ping"})
    assert w.payload == {"event": "ping"}


def test_rejects_oversized_payload():
    """A payload over the size limit is rejected."""
    big = {"data": "x" * 300_000}  # exceeds 256KB
    with pytest.raises(ValidationError):
        WebhookIn(target_url="https://example.com/hook", payload=big)


def test_event_out_serializes_from_model_instance():
    """EventOut reads its fields directly off an Event ORM instance."""
    event = Event(
        id=uuid.uuid4(),
        status="pending",
        target_url="https://example.com/hook",
        attempts_count=0,
        created_at=datetime.now(timezone.utc),
    )

    out = EventOut.model_validate(event)

    assert out.id == event.id
    assert out.status == "pending"
    assert out.target_url == "https://example.com/hook"
    assert out.attempts_count == 0


def test_event_detail_out_serializes_nested_delivery_attempts():
    """EventDetailOut includes delivery attempts nested under the event."""
    event = Event(
        id=uuid.uuid4(),
        status="dead",
        target_url="https://example.com/hook",
        attempts_count=1,
        max_retries=5,
        next_attempt_at=None,
        created_at=datetime.now(timezone.utc),
    )
    event.delivery_attempts = [
        DeliveryAttempt(
            attempt_number=1,
            response_status_code=500,
            response_body="error",
            error_message=None,
            attempted_at=datetime.now(timezone.utc),
        )
    ]

    out = EventDetailOut.model_validate(event)

    assert len(out.delivery_attempts) == 1
    assert out.delivery_attempts[0].response_status_code == 500
    assert out.delivery_attempts[0].attempt_number == 1
