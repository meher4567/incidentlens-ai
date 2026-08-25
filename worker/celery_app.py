from celery import Celery

from backend.app.core.config import get_settings

settings = get_settings()

app = Celery(
    "incidentlens",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "worker.tasks.aggregation",
        "worker.tasks.detection",
        "worker.tasks.alerting",
        "worker.tasks.incident_pipeline",
    ],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=270,
    task_time_limit=300,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    broker_connection_retry_on_startup=True,
    task_default_queue="celery",
    task_routes={
        "worker.tasks.aggregation.*": {"queue": "aggregate"},
        "worker.tasks.detection.*": {"queue": "detect"},
        "worker.tasks.alerting.*": {"queue": "detect"},
        "worker.tasks.incident_pipeline.*": {"queue": "detect"},
    },
    beat_schedule={
        "run-aggregation-every-30s": {
            "task": "worker.tasks.aggregation.aggregate_windows",
            "schedule": 30.0,
        },
    },
)
