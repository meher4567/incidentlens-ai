"""
Alerting worker task.

Converts anomalies into alerts with debounce and severity grading.
"""
from celery.utils.log import get_task_logger

from backend.app.db.session import SyncSessionLocal
from backend.app.services.alerting import process_new_anomalies
from worker.celery_app import app

logger = get_task_logger(__name__)


@app.task(name="worker.tasks.alerting.process_anomalies")
def process_anomalies():
    """Convert new anomalies into alerts with debounce and severity."""
    logger.info("Alert processing task triggered")
    session = SyncSessionLocal()
    try:
        count = process_new_anomalies(session)
        logger.info(f"Alert processing complete: {count} alerts processed")
        # Chain: after alerting, run dedup + clustering
        from worker.tasks.incident_pipeline import deduplicate_and_cluster

        deduplicate_and_cluster.delay()
        return {"status": "ok", "alerts_processed": count}
    except Exception as exc:
        logger.error(f"Alert processing failed: {exc}")
        raise
    finally:
        session.close()
