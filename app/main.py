from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel, HttpUrl
from sqlalchemy import text

from app.database import engine


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
    target_url: HttpUrl
    payload: dict

@app.post("/api/v1/events", status_code=202)
def create_event(webhook: WebhookIn):
    return {"id": uuid4(), 
            "status": "pending"}
