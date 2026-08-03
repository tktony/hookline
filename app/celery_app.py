import os

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "hookline",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.autodiscover_tasks(["app.worker"])

celery_app.conf.beat_schedule = {
    "poll-retries-every-60s": {
        "task": "app.worker.poll_retries",
        "schedule": 60.0,
    },
}
