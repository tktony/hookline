from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine, get_session
from app.models import Event
from app.worker import deliver_event

DEV_API_KEY_ID = UUID("14fb582f-5a23-4c76-8378-7890bf3789ca")  # TODO: replace with real key from auth

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        print("db connection ok:", result.scalar())
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok"}

class WebhookIn(BaseModel):
    """ Input payload for creating a webhook event """
    target_url: HttpUrl
    payload: dict

class EventOut(BaseModel):
    """ Pydantic response model = Serializer: model->JSON """
    id: UUID
    status: str
    target_url: str
    attempts_count: int
    created_at: datetime

    model_config = {"from_attributes": True}

@app.post("/api/v1/events", status_code=202, response_model=EventOut)
async def create_event(webhook: WebhookIn, session: Annotated[AsyncSession, Depends(get_session)]): 
    event = Event(
        api_key_id=DEV_API_KEY_ID,
        target_url=str(webhook.target_url),
        payload=webhook.payload
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    deliver_event.delay(str(event.id)) # Celery
    return event

@app.get("/api/v1/events/{id}", response_model=EventOut)
async def get_event(id: UUID, session: Annotated[AsyncSession, Depends(get_session)]):
    event = await session.get(Event, id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    return event

# TODO: Pagination
@app.get("/api/v1/events", response_model=list[EventOut])
async def list_events(session: Annotated[AsyncSession, Depends(get_session)], status: str | None = None):
    stmt = select(Event)
    if status is not None:
        stmt = stmt.where(Event.status == status)
    result = await session.execute(stmt)
    return result.scalars().all()