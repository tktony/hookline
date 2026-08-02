import httpx

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import DeliveryAttempt, Event


@celery_app.task
def deliver_event(event_id: str):
    session = SessionLocal()
    try:
        event = session.get(Event, event_id)
        if event is None:
            return 

        # 1. Make the POST to event.target_url with event.payload
        #    Use httpx with a timeout. Wrap in try/except to catch failures.
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

        # 2. Create a DeliveryAttempt row recording what happened
        #    (attempt_number, response_status_code, response_body, error_message)
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
        #    success (2xx) -> "success", else retry logic
        if status_code is not None and 200 <= status_code < 300:
            event.status = "success"

        session.commit()
    finally:
        session.close()