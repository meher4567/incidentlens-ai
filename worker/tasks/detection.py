"""
Detection worker task.

Triggered after aggregation.
Runs MAD detection on newly-closed metric windows.
"""
from celery.utils.log import get_task_logger

from backend.app.db.session import SyncSessionLocal
from backend.app.services.detection import run_detection_all
from worker.celery_app import app

logger = get_task_logger(__name__)


@app.task(name="worker.tasks.detection.run_detection")
def run_detection(window_start=None, window_size_seconds=None):
    """Run anomaly detection on all ready metric windows."""
    logger.info(f"Detection task triggered for window_start={window_start}")
    session = SyncSessionLocal()
    try:
        anomalies = run_detection_all(session)
        logger.info(f"Detection complete: {anomalies} anomalies found")
        # Chain: after detection, run alerting
        from worker.tasks.alerting import process_anomalies

        process_anomalies.delay()
        return {"status": "ok", "anomalies_found": anomalies}
    except Exception as exc:
        logger.error(f"Detection failed: {exc}")
        raise
    finally:
        session.close()
