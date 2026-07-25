import os
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, HttpUrl

load_dotenv() 
DATABASE_URL = os.environ["DATABASE_URL"]

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