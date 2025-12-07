import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "daily_knowledge_feed",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["workers.tasks"]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task (for long podcasts)
    worker_prefetch_multiplier=1,  # Process one task at a time
    worker_concurrency=2,  # Limit workers for Railway's memory constraints
)

# Scheduled tasks
celery_app.conf.beat_schedule = {
    # Poll all sources every hour
    "poll-sources-hourly": {
        "task": "workers.tasks.poll_all_sources",
        "schedule": crontab(minute=0),  # Every hour at :00
    },
    # Check for digests to send every hour
    "send-digests-hourly": {
        "task": "workers.tasks.send_scheduled_digests",
        "schedule": crontab(minute=5),  # Every hour at :05
    },
}
