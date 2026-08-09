"""SQLAlchemy models for API keys, webhook events, and delivery attempts."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    label: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    events: Mapped[list["Event"]] = relationship(back_populates="api_key")


class Event(Base):
    __tablename__ = "events"

    # Index status and retry time together to efficiently find events due for delivery.
    __table_args__ = (
        Index("ix_events_status_next_attempt_at", "status", "next_attempt_at"), # trailing comma -> tuple
        ) 

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    api_key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("api_keys.id", ondelete="CASCADE"), index=True)
    target_url: Mapped[str] = mapped_column(String(2048))
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(default="pending")
    attempts_count: Mapped[int] = mapped_column(default=0)
    max_retries: Mapped[int] = mapped_column(default=5)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    api_key: Mapped["ApiKey"] = relationship(back_populates="events")
    delivery_attempts: Mapped[list["DeliveryAttempt"]] = relationship(back_populates="event")


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    attempt_number: Mapped[int]
    response_status_code: Mapped[int | None]
    response_body: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped["Event"] = relationship(back_populates="delivery_attempts")
