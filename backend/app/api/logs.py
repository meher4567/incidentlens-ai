import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.db.session import get_sync_session
from backend.app.models.logs import RawLog
from backend.app.models.services import Service
from backend.app.schemas.logs import (
    LogBatch,
    LogBatchResponse,
    LogEntry,
    LogError,
)

router = APIRouter()


def _get_service_id_by_name(session: Session, name: str) -> uuid.UUID:
    service = session.execute(select(Service.id).where(Service.name == name)).scalar_one_or_none()
    if service is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found")
    return service


def _log_entry_to_model(entry: LogEntry, service_id: uuid.UUID) -> RawLog:
    return RawLog(
        service_id=service_id,
        timestamp=entry.timestamp,
        level=entry.level,
        message=entry.message,
        request_id=entry.request_id,
        trace_id=entry.trace_id,
        latency_ms=entry.latency_ms,
        status_code=entry.status_code,
        extra_data={
            "host": entry.host,
            "region": entry.region,
        }
        if entry.host or entry.region
        else None,
    )


@router.post("/batch", response_model=LogBatchResponse, status_code=201)
def ingest_batch(
    batch: LogBatch,
    session: Session = Depends(get_sync_session),
):
    """
    Ingest a batch of up to 1000 log events.
    Returns count of successfully ingested events and any validation errors.
    """
    ingested = 0
    errors: list[LogError] = []

    # Pre-fetch service name->id mapping for efficiency
    service_names = {e.service for e in batch.events}
    service_rows = session.execute(
        select(Service.name, Service.id).where(Service.name.in_(service_names))
    ).all()
    existing_services: dict[str, uuid.UUID] = {
        name: service_id for name, service_id in service_rows
    }

    rows_to_insert = []
    for i, entry in enumerate(batch.events):
        try:
            service_id = existing_services.get(entry.service)
            if service_id is None:
                # Auto-create unknown services
                created_service = Service(name=entry.service)
                session.add(created_service)
                session.flush()
                service_id = created_service.id
                existing_services[entry.service] = service_id

            rows_to_insert.append(_log_entry_to_model(entry, service_id))
            ingested += 1
        except Exception as exc:
            errors.append(LogError(index=i, message=str(exc)))

    if rows_to_insert:
        try:
            session.add_all(rows_to_insert)
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            raise HTTPException(status_code=503, detail="Log storage unavailable") from exc

    return LogBatchResponse(ingested=ingested, errors=errors)


@router.post("/single", status_code=201)
def ingest_single(
    entry: LogEntry,
    session: Session = Depends(get_sync_session),
):
    """Ingest a single log event."""
    try:
        service_id = _get_service_id_by_name(session, entry.service)
    except HTTPException:
        svc = Service(name=entry.service)
        session.add(svc)
        session.flush()
        service_id = svc.id

    log = _log_entry_to_model(entry, service_id)
    session.add(log)
    session.commit()
    return {"id": log.id}


@router.get("")
def query_logs(
    service: str | None = Query(None),
    level: str | None = Query(None, pattern="^(DEBUG|INFO|WARN|ERROR|CRITICAL)$"),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    trace_id: uuid.UUID | None = Query(None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_sync_session),
):
    """Query raw logs with filters."""
    stmt = select(RawLog)

    if service:
        svc_id = _get_service_id_by_name(session, service)
        stmt = stmt.where(RawLog.service_id == svc_id)
    if level:
        stmt = stmt.where(RawLog.level == level.upper())
    if start_time:
        stmt = stmt.where(RawLog.timestamp >= start_time)
    if end_time:
        stmt = stmt.where(RawLog.timestamp <= end_time)
    if trace_id:
        stmt = stmt.where(RawLog.trace_id == trace_id)

    stmt = stmt.order_by(RawLog.timestamp.desc()).offset(offset).limit(limit)
    result = session.execute(stmt).scalars().all()
    return result


@router.get("/by-trace/{trace_id}")
def get_logs_by_trace(
    trace_id: uuid.UUID,
    session: Session = Depends(get_sync_session),
):
    """Get all logs for a given trace_id."""
    stmt = select(RawLog).where(RawLog.trace_id == trace_id).order_by(RawLog.timestamp.asc())
    result = session.execute(stmt).scalars().all()
    if not result:
        raise HTTPException(status_code=404, detail="Trace not found")
    return result


@router.get("/counts")
def get_log_counts(
    session: Session = Depends(get_sync_session),
):
    """Get total log count and recent ingestion rate."""
    total = session.execute(select(func.count(RawLog.id))).scalar()
    return {"total_logs": total}
