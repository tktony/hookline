import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import or_, select

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



def is_safe_url(url: str) -> bool:
    hostname = urlparse(url).hostname
    if hostname is None:
        return False
    try:
        ip_str = socket.gethostbyname(hostname)
    except socket.gaierror:
        return False  # can't resolve = don't trust it
    ip = ipaddress.ip_address(ip_str)
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)



@celery_app.task
def deliver_event(event_id: str):
    session = SessionLocal()
    try:
        event = session.get(Event, event_id)
        if event is None:
            return 

        # SSRF Gurad
        if not is_safe_url(event.target_url):
            attempt = DeliveryAttempt(
                event_id=event_id,
                attempt_number=event.attempts_count + 1,
                response_status_code=None,
                response_body=None,
                error_message="blocked: target resolves to a private or internal address",
            )
            session.add(attempt)
            event.attempts_count += 1
            event.status = "dead"
            session.commit()
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
        grace = now - timedelta(minutes=5) # lost claim rescued after 5 minutes instead of orphaning
        stmt = select(Event).where(
            or_(
            (Event.status == "retrying") & (Event.next_attempt_at <= now),
            (Event.status == "queued") & (Event.next_attempt_at <= grace),
            )
        )
        due_events = session.execute(stmt).scalars().all()

        # Claim all of them, then commit
        for event in due_events:
            event.status = "queued"
            event.next_attempt_at = now   # stamp claim time
        session.commit()

        # Now that the claim is committed, enqueue
        for event in due_events:
            deliver_event.delay(str(event.id))
    finally:
        session.close()