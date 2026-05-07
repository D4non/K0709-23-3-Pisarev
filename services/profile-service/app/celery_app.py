"""
Celery application instance for the rating-aggregator component.

Uses Redis as both broker (task queue) and backend (result storage).
Celery Beat schedules two periodic tasks:
  - recompute_behavioral_scores: every 30 minutes
  - recompute_combined_snapshots: every hour
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from celery import Celery
from shared.config import settings

celery_app = Celery(
    "rating-aggregator",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.recompute"],
)

celery_app.conf.beat_schedule = {
    # Level 2: пересчёт поведенческих счётчиков каждые 30 минут
    "recompute-behavioral-every-30min": {
        "task": "app.tasks.recompute.recompute_behavioral_scores",
        "schedule": 1800.0,
    },
    # Level 3: пересчёт комбинированных снапшотов раз в час
    "recompute-snapshots-every-hour": {
        "task": "app.tasks.recompute.recompute_combined_snapshots",
        "schedule": 3600.0,
    },
}

celery_app.conf.timezone = "UTC"
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1
