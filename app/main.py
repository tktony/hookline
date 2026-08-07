import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, HttpUrl, field_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine, get_session
from app.models import ApiKey, Event
from app.worker import deliver_event

MAX_PAYLOAD_BYTES = 256_000  # 256 KB
bearer_scheme = HTTPBearer()

async def require_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApiKey:
    raw_key = credentials.credentials
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
    result = await session.execute(stmt)
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    return api_key

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

    @field_validator("payload")
    @classmethod
    def payload_not_too_large(cls, v: dict) -> dict:
        payload_bytes = len(json.dumps(v, ensure_ascii=False).encode("utf-8"))
        if payload_bytes > MAX_PAYLOAD_BYTES:
            raise ValueError(f"Payload exceeds {MAX_PAYLOAD_BYTES} bytes")
        return v


class EventOut(BaseModel):
    """ Pydantic response model = Serializer: model->JSON """
    id: UUID
    status: str
    target_url: str
    attempts_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


@app.post("/api/v1/events", status_code=202, response_model=EventOut)
async def create_event(
    webhook: WebhookIn, 
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[ApiKey, Depends(require_api_key)]
    ): 
    event = Event(
        api_key_id=api_key.id,
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