"""Prometheus metrics endpoint for monitoring webhook event delivery."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Event

router = APIRouter()

events_by_status = Gauge(
    "hookline_events_by_status",
    "Number of events grouped by status",
    ["status"],
)

@router.get("/metrics")
async def metrics(session: Annotated[AsyncSession, Depends(get_session)]):
    """Return current webhook event counts in Prometheus format."""

    # Aggregate event counts by status to expose them as Prometheus labels.
    stmt = select(Event.status, func.count(Event.id)).group_by(Event.status)
    result = await session.execute(stmt)
    rows = result.all()

    # Replace previous metric values with the current database state.
    events_by_status.clear()
    for status, count in rows:
        events_by_status.labels(status=status).set(count)

    # Return metrics using Prometheus's expected exposition format.
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)