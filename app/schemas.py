"""Pydantic schemas for webhook event input and API responses."""

import json
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, HttpUrl, field_validator

from app.config import MAX_PAYLOAD_BYTES


class WebhookIn(BaseModel):
    """Validate incoming webhook event data."""

    target_url: HttpUrl
    payload: dict

    @field_validator("payload")
    @classmethod
    def payload_not_too_large(cls, v: dict) -> dict:
        """Reject payloads that exceed the configured size limit."""

        # Measure the serialized payload size using UTF-8 encoded JSON.
        payload_bytes = len(json.dumps(v, ensure_ascii=False).encode("utf-8"))

        if payload_bytes > MAX_PAYLOAD_BYTES:
            raise ValueError(f"Payload exceeds {MAX_PAYLOAD_BYTES} bytes")
        
        return v


class EventOut(BaseModel):
    """Serialize webhook event summary data for API responses."""

    id: UUID
    status: str
    target_url: str
    attempts_count: int
    created_at: datetime

    # Enable validation directly from SQLAlchemy model attributes.
    model_config = {"from_attributes": True}


class DeliveryAttemptOut(BaseModel):
    """Serialize individual delivery attempt data for API responses."""

    attempt_number: int
    response_status_code: int | None
    response_body: str | None
    error_message: str | None
    attempted_at: datetime

    model_config = {"from_attributes": True}


class EventDetailOut(BaseModel):
    """Serialize detailed webhook event data including delivery attempts."""

    id: UUID
    status: str
    target_url: str
    attempts_count: int
    max_retries: int
    next_attempt_at: datetime | None
    created_at: datetime
    delivery_attempts: list[DeliveryAttemptOut]

    model_config = {"from_attributes": True}