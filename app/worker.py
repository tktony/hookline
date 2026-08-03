from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import DeliveryAttempt, Event

BACKOFF_SCHEDULE = [
    60,     # 1 minute
    300,    # 5 minutes
    900,    # 15 minutes
    1800,   # 30 minutes
    3600,   # 60 minutes
]

@celery_app.task
def deliver_event(event_id: str):
    session = SessionLocal()
    try:
        event = session.get(Event, event_id)
        if event is None:
            return 

        # 1. Make the POST to event.target_url with event.payload: Use httpx with a timeout
        status_code = None
        body = None
        error = None
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(event.target_url, json=event.payload)
            status_code = response.status_code
            body = response.text
        except httpx.RequestError as exc:
            error = str(exc)

        # 2. Create a DeliveryAttempt row recording what happened: (attempt_number, response_status_code, response_body, error_message)
        delivery_attempt = DeliveryAttempt(
            event_id=event_id,
            attempt_number=event.attempts_count + 1,
            response_status_code=status_code,
            response_body=body,
            error_message=error
        )
        session.add(delivery_attempt)
        event.attempts_count += 1

        # 3. Update event.status based on outcome
        
        # SUCCESS
        if status_code is not None and 200 <= status_code < 300:
            event.status = "success"
        # DEAD
        elif event.attempts_count >= event.max_retries:
            event.status = "dead"
            # TODO: Dead letter extensions if needed
        # RETRY
        else:
            # timestamp into the future 
            delay = BACKOFF_SCHEDULE[min(event.attempts_count - 1, len(BACKOFF_SCHEDULE) - 1)]
            event.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            event.status = "retrying"
        

        session.commit()
    finally:
        session.close()



@celery_app.task
def poll_retries():
    session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        stmt = select(Event).where(Event.status == "retrying", Event.next_attempt_at <= now)
        due_events = session.execute(stmt).scalars().all()

        # Claim all of them, then commit
        for event in due_events:
            event.status = "queued"
        session.commit()

        # Now that the claim is committed, enqueue
        for event in due_events:
            deliver_event.delay(str(event.id))
    finally:
        session.close()