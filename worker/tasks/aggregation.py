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


@app.task(name="worker.tasks.aggregation.aggregate_windows")
def aggregate_windows():
    """Periodic task: aggregate raw_logs into metric_windows."""
    logger.info("Aggregation task triggered")
    session = SyncSessionLocal()
    try:
        windows = run_aggregation_all_services(session)
        logger.info(f"Aggregation complete: {windows} windows computed")
        return {"status": "ok", "windows_computed": windows}
    except Exception as exc:
        logger.error(f"Aggregation failed: {exc}")
        raise
    finally:
        session.close()
