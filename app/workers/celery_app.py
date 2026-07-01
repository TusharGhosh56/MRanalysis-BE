import sys

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "github_analytics",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

# prefork (default) uses multiprocessing and fails on Windows with PermissionError.
_worker_pool = "solo" if sys.platform == "win32" else "prefork"

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_pool=_worker_pool,
    worker_concurrency=1 if sys.platform == "win32" else None,
)