"""FastAPI application setup, startup checks, and router registration."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine
from app.metrics import router as metrics_router
from app.routers import events, health

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify database connectivity during application startup."""

    # Confirm that the database is reachable before accepting requests.
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        logger.info("Database connection successful: %s", result.scalar())

    yield

app = FastAPI(lifespan=lifespan)
app.include_router(health.router)
app.include_router(metrics_router) 
app.include_router(events.router)