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


@app.task(
    name="worker.tasks.incident_pipeline.deduplicate_and_cluster",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def deduplicate_and_cluster():
    """Run deduplication on new alerts, then cluster into incidents."""
    logger.info("Deduplication + clustering task triggered")
    session = SyncSessionLocal()
    try:
        dedup_count = deduplicate_alerts(session)
        logger.info("Deduplication complete: %s relationships created", dedup_count)

        incident_count = cluster_alerts(session)
        logger.info("Clustering complete: %s incidents created/updated", incident_count)

        # Chain: after clustering, run RCA on newly-closed incidents
        score_root_causes.delay()
        return {
            "status": "ok",
            "dedup_count": dedup_count,
            "incident_count": incident_count,
        }
    except Exception as exc:
        session.rollback()
        logger.exception("Dedup/clustering failed: %s", exc)
        raise
    finally:
        session.close()


@app.task(
    name="worker.tasks.incident_pipeline.score_root_causes",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def score_root_causes(incident_id=None):
    """Run RCA ranker on closed incidents."""
    logger.info("RCA ranking task triggered for incident=%s", incident_id)
    session = SyncSessionLocal()
    try:
        scored = run_rca_on_closed_incidents(session)
        logger.info("RCA ranking complete: %s incidents scored", scored)
        return {"status": "ok", "incidents_scored": scored}
    except Exception as exc:
        session.rollback()
        logger.exception("RCA ranking failed: %s", exc)
        raise
    finally:
        session.close()
