from fastapi import APIRouter

from backend.app.api import alerts, anomalies, health, incidents, logs, metrics, services

router = APIRouter()

router.include_router(logs.router, prefix="/logs", tags=["logs"])
router.include_router(services.router, prefix="/services", tags=["services"])
router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
router.include_router(anomalies.router, prefix="/anomalies", tags=["anomalies"])
router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
router.include_router(incidents.router, prefix="/incidents", tags=["incidents"])
router.include_router(health.router, tags=["health"])
