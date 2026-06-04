"""
Incident pipeline worker tasks.

Handles deduplication, clustering, and RCA ranking in sequence.
"""
from celery.utils.log import get_task_logger

from backend.app.db.session import SyncSessionLocal
from backend.app.services.clustering import cluster_alerts
from backend.app.services.deduplication import deduplicate_alerts
from backend.app.services.root_cause import run_rca_on_closed_incidents
from worker.celery_app import app

logger = get_task_logger(__name__)


@app.task(name="worker.tasks.incident_pipeline.deduplicate_and_cluster")
def deduplicate_and_cluster():
    """Run deduplication on new alerts, then cluster into incidents."""
    logger.info("Deduplication + clustering task triggered")
    session = SyncSessionLocal()
    try:
        dedup_count = deduplicate_alerts(session)
        logger.info(f"Deduplication complete: {dedup_count} relationships created")

        incident_count = cluster_alerts(session)
        logger.info(f"Clustering complete: {incident_count} incidents created/updated")

        # Chain: after clustering, run RCA on newly-closed incidents
        score_root_causes.delay()
        return {
            "status": "ok",
            "dedup_count": dedup_count,
            "incident_count": incident_count,
        }
    except Exception as exc:
        logger.error(f"Dedup/clustering failed: {exc}")
        raise
    finally:
        session.close()


@app.task(name="worker.tasks.incident_pipeline.score_root_causes")
def score_root_causes(incident_id=None):
    """Run RCA ranker on closed incidents."""
    logger.info(f"RCA ranking task triggered for incident={incident_id}")
    session = SyncSessionLocal()
    try:
        scored = run_rca_on_closed_incidents(session)
        logger.info(f"RCA ranking complete: {scored} incidents scored")
        return {"status": "ok", "incidents_scored": scored}
    except Exception as exc:
        logger.error(f"RCA ranking failed: {exc}")
        raise
    finally:
        session.close()
