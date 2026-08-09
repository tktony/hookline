from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine
from app.metrics import router as metrics_router
from app.routers import events, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        print("db connection ok:", result.scalar())
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(health.router)
app.include_router(metrics_router) 
app.include_router(events.router)