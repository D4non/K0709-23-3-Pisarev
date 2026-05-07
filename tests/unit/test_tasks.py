"""
Unit tests for Celery configuration and task registration (app/celery_app.py,
app/tasks/recompute.py).

Tests do NOT start a real Celery worker or connect to Redis — they verify
that tasks are correctly registered and the beat schedule is configured as
described in the README.
"""
import pytest


def test_both_tasks_are_registered_in_celery():
    """Both periodic tasks must be discoverable by the Celery worker."""
    from app.celery_app import celery_app
    import app.tasks.recompute  # noqa: F401 — ensures tasks are registered

    registered = set(celery_app.tasks.keys())
    assert "app.tasks.recompute.recompute_behavioral_scores" in registered
    assert "app.tasks.recompute.recompute_combined_snapshots" in registered


def test_beat_schedule_has_both_entries():
    """Celery Beat must schedule both recompute tasks."""
    from app.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "recompute-behavioral-every-30min" in schedule
    assert "recompute-snapshots-every-hour" in schedule


def test_behavioral_task_runs_every_30_minutes():
    from app.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["recompute-behavioral-every-30min"]
    assert entry["task"] == "app.tasks.recompute.recompute_behavioral_scores"
    assert entry["schedule"] == 1800.0


def test_snapshots_task_runs_every_hour():
    from app.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["recompute-snapshots-every-hour"]
    assert entry["task"] == "app.tasks.recompute.recompute_combined_snapshots"
    assert entry["schedule"] == 3600.0


def test_celery_uses_redis_as_broker():
    from app.celery_app import celery_app
    from shared.config import settings

    assert celery_app.conf.broker_url == settings.REDIS_URL


def test_celery_task_serializer_is_json():
    from app.celery_app import celery_app

    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"


def test_task_acks_late_is_enabled():
    """Tasks should be acknowledged only after successful completion."""
    from app.celery_app import celery_app

    assert celery_app.conf.task_acks_late is True
