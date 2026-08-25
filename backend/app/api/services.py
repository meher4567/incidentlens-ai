import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from backend.app.db.session import get_sync_session
from backend.app.models.metrics import MetricWindow
from backend.app.models.services import Service, ServiceDependency
from backend.app.schemas.metrics import MetricWindowResponse, ServiceHealthResponse
from backend.app.schemas.services import (
    DependencyCreate,
    DependencyResponse,
    ServiceCreate,
    ServiceResponse,
)

router = APIRouter()


@router.post("", response_model=ServiceResponse, status_code=201)
def create_service(
    payload: ServiceCreate,
    session: Session = Depends(get_sync_session),
):
    """Create a new service."""
    existing = session.execute(
        select(Service).where(Service.name == payload.name)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Service already exists")
    svc = Service(name=payload.name)
    session.add(svc)
    session.commit()
    session.refresh(svc)
    return svc


@router.get("", response_model=list[ServiceResponse])
def list_services(
    session: Session = Depends(get_sync_session),
):
    """List all services."""
    result = session.execute(select(Service).order_by(Service.name))
    return result.scalars().all()


@router.post("/dependencies", status_code=201)
def create_dependency(
    payload: DependencyCreate,
    session: Session = Depends(get_sync_session),
):
    """Create a dependency edge (upstream -> downstream)."""
    if payload.upstream == payload.downstream:
        raise HTTPException(status_code=400, detail="A service cannot depend on itself")

    upstream = session.execute(
        select(Service).where(Service.name == payload.upstream)
    ).scalar_one_or_none()
    if not upstream:
        raise HTTPException(
            status_code=404, detail=f"Upstream service '{payload.upstream}' not found"
        )
    downstream = session.execute(
        select(Service).where(Service.name == payload.downstream)
    ).scalar_one_or_none()
    if not downstream:
        raise HTTPException(
            status_code=404, detail=f"Downstream service '{payload.downstream}' not found"
        )

    existing = session.execute(
        select(ServiceDependency).where(
            ServiceDependency.upstream_id == upstream.id,
            ServiceDependency.downstream_id == downstream.id,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Dependency already exists")

    dep = ServiceDependency(upstream_id=upstream.id, downstream_id=downstream.id)
    session.add(dep)
    session.commit()
    return DependencyResponse(
        upstream_id=upstream.id,
        downstream_id=downstream.id,
        upstream_name=upstream.name,
        downstream_name=downstream.name,
    )


@router.get("/dependencies", response_model=list[DependencyResponse])
def list_dependencies(
    session: Session = Depends(get_sync_session),
):
    """List all dependency edges."""
    upstream = aliased(Service)
    downstream = aliased(Service)
    stmt = (
        select(
            ServiceDependency.upstream_id,
            ServiceDependency.downstream_id,
            upstream.name.label("upstream_name"),
            downstream.name.label("downstream_name"),
        )
        .join(upstream, ServiceDependency.upstream_id == upstream.id)
        .join(downstream, ServiceDependency.downstream_id == downstream.id)
        .order_by(upstream.name, downstream.name)
    )
    rows = session.execute(stmt).all()
    return [
        DependencyResponse(
            upstream_id=r.upstream_id,
            downstream_id=r.downstream_id,
            upstream_name=r.upstream_name,
            downstream_name=r.downstream_name,
        )
        for r in rows
    ]


@router.get("/{service_id}/health", response_model=ServiceHealthResponse)
def get_service_health(
    service_id: uuid.UUID,
    window_size_seconds: int = Query(default=60, ge=60, le=300),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    limit: int = Query(default=200, ge=1, le=1000),
    session: Session = Depends(get_sync_session),
):
    """Get service health metrics as time-series windows."""
    service = session.execute(select(Service).where(Service.id == service_id)).scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    stmt = select(MetricWindow).where(
        MetricWindow.service_id == service_id,
        MetricWindow.window_size_seconds == window_size_seconds,
    )
    if start_time:
        stmt = stmt.where(MetricWindow.window_start >= start_time)
    if end_time:
        stmt = stmt.where(MetricWindow.window_start <= end_time)

    stmt = stmt.order_by(MetricWindow.window_start.asc()).limit(limit)
    windows = session.execute(stmt).scalars().all()

    return ServiceHealthResponse(
        service_id=service.id,
        service_name=service.name,
        windows=[MetricWindowResponse.model_validate(w) for w in windows],
        window_size_seconds=window_size_seconds,
    )
