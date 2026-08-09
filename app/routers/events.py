from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models import ApiKey, Event
from app.ratelimit import rate_limit
from app.schemas import EventDetailOut, EventOut, WebhookIn
from app.security import require_api_key
from app.worker import deliver_event

router = APIRouter(prefix="/api/v1")

# demo page polls this endpoint
@router.get("/events/{id}/detail", response_model=EventDetailOut)
async def get_event_detail(
    id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
):
    stmt = (
        select(Event)
        .where(Event.id == id)
        .options(selectinload(Event.delivery_attempts))
    )
    result = await session.execute(stmt)
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    return event


@router.post(
    "/events",
    status_code=202,
    response_model=EventOut,
    dependencies=[Depends(rate_limit)],
)
async def create_event(
    webhook: WebhookIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[ApiKey, Depends(require_api_key)],
):
    event = Event(
        api_key_id=api_key.id,
        target_url=str(webhook.target_url),
        payload=webhook.payload,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    deliver_event.delay(str(event.id)) # Celery
    return event


@router.get("/events/{id}", response_model=EventOut)
async def get_event(id: UUID, session: Annotated[AsyncSession, Depends(get_session)]):
    event = await session.get(Event, id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    return event


@router.get("/events", response_model=list[EventOut])
async def list_events(
    session: Annotated[AsyncSession, Depends(get_session)],
    status: str | None = None,
    limit: int = Query(50, ge=1, le=100), # must be between 1-100
    offset: int = Query(0, ge=0), # def=0, not 0<
):
    stmt = select(Event)
    if status is not None:
        stmt = stmt.where(Event.status == status)
    stmt = stmt.order_by(Event.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return result.scalars().all()