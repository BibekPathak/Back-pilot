"""Celery application used to run agent workflows asynchronously."""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "backpilot",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

# Import tasks so they register with the worker.
import app.agents.tasks  # noqa: E402, F401
