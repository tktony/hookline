"""Tests for the events API endpoints."""

import hashlib
import uuid
from unittest.mock import AsyncMock, patch

from app.models import ApiKey, Event


async def _create_api_key(session, raw_key: str = "test-key-valid") -> ApiKey:
    """Insert an active API key and return it, hashed the way require_api_key expects."""
    api_key = ApiKey(key_hash=hashlib.sha256(raw_key.encode()).hexdigest(), label="test")
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return api_key


async def _create_event(session, api_key_id, **overrides) -> Event:
    """Insert an event owned by the given API key, committed on its own."""
    defaults = {"target_url": "https://example.com/hook", "payload": {}}
    defaults.update(overrides)
    event = Event(api_key_id=api_key_id, **defaults)
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def test_post_without_key_is_rejected(client):
    """POST /events without an API key returns 401 or 403."""
    resp = await client.post(
        "/api/v1/events",
        json={"target_url": "https://example.com/hook", "payload": {"x": 1}},
    )
    assert resp.status_code in (401, 403)


async def test_post_with_valid_key_creates_event(client, db_session):
    """POST /events with a valid API key returns 202 and persists the event."""
    raw_key = "test-key-valid"
    await _create_api_key(db_session, raw_key)

    with (
        patch("app.routers.events.deliver_event.delay") as mock_delay,
        patch("app.ratelimit.redis_client.incr", new=AsyncMock(return_value=1)),
        patch("app.ratelimit.redis_client.expire", new=AsyncMock(return_value=True)),
    ):
        resp = await client.post(
            "/api/v1/events",
            json={"target_url": "https://example.com/hook", "payload": {"x": 1}},
            headers={"Authorization": f"Bearer {raw_key}"},
        )

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert body["target_url"] == "https://example.com/hook"
    mock_delay.assert_called_once_with(body["id"])


async def test_list_events_empty(client):
    """GET /events returns an empty list on a fresh database."""
    resp = await client.get("/api/v1/events")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_event_not_found(client):
    """GET /events/{id} returns 404 for a nonexistent event."""
    resp = await client.get(f"/api/v1/events/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_list_events_filters_by_status(client, db_session):
    """GET /events?status= only returns events matching that status."""
    api_key = await _create_api_key(db_session)
    await _create_event(db_session, api_key.id, status="pending")
    await _create_event(db_session, api_key.id, status="dead")
    await _create_event(db_session, api_key.id, status="dead")

    resp = await client.get("/api/v1/events", params={"status": "dead"})

    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 2
    assert all(e["status"] == "dead" for e in events)


async def test_list_events_pagination(client, db_session):
    """GET /events respects limit and offset without overlapping pages."""
    api_key = await _create_api_key(db_session)
    for _ in range(5):
        await _create_event(db_session, api_key.id)

    first_page = await client.get("/api/v1/events", params={"limit": 2, "offset": 0})
    second_page = await client.get("/api/v1/events", params={"limit": 2, "offset": 2})

    assert len(first_page.json()) == 2
    assert len(second_page.json()) == 2
    first_ids = {e["id"] for e in first_page.json()}
    second_ids = {e["id"] for e in second_page.json()}
    assert first_ids.isdisjoint(second_ids)


async def test_list_events_limit_over_max_is_rejected(client):
    """GET /events?limit=999 exceeds the allowed maximum and is rejected."""
    resp = await client.get("/api/v1/events", params={"limit": 999})
    assert resp.status_code == 422
