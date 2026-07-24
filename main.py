from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel, HttpUrl

app = FastAPI()

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