"""
Aggregation worker task.

Runs every 30 seconds via Celery Beat.
Computes 1-min and 5-min metric windows from raw_logs.
"""

from celery.utils.log import get_task_logger

from backend.app.db.session import SyncSessionLocal
from backend.app.services.aggregation import run_aggregation_all_services
from worker.celery_app import app

logger = get_task_logger(__name__)


@app.task(
    name="worker.tasks.aggregation.aggregate_windows",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def aggregate_windows():
    """Periodic task: aggregate raw_logs into metric_windows."""
    logger.info("Aggregation task triggered")
    session = SyncSessionLocal()
    try:
        windows = run_aggregation_all_services(session)
        logger.info("Aggregation complete: %s windows computed", windows)
        if windows > 0:
            from worker.tasks.detection import run_detection

            run_detection.delay()
        return {"status": "ok", "windows_computed": windows}
    except Exception as exc:
        session.rollback()
        logger.exception("Aggregation failed: %s", exc)
        raise
    finally:
        session.close()
