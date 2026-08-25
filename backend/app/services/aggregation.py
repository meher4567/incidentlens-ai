"""
Metric window aggregation service.

Computes 1-min and 5-min metric windows from raw_logs,
maintains rolling baselines (median + MAD), and handles
late-arriving logs via UPSERT idempotency.

Uses event time for window assignment. Ingestion time stored separately.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.logs import RawLog
from backend.app.models.metrics import MetricWindow
from backend.app.models.services import Service
from backend.app.models.watermark import Watermark

settings = get_settings()

WINDOW_SIZES = [60, 300]  # 1-minute, 5-minute
BASELINE_WINDOWS = settings.baseline_window_count  # 30
GRACE_MINUTES = settings.watermark_grace_minutes  # 5


def _as_utc(dt: datetime) -> datetime:
    """Normalize DB datetimes to aware UTC; SQLite drops timezone metadata."""
    if dt.tzinfo is None or dt.utcoffset() is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_postgres(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


def floor_dt(dt: datetime, seconds: int) -> datetime:
    """Floor a datetime to the nearest window boundary."""
    dt = _as_utc(dt)
    ts = dt.timestamp()
    floored = (int(ts) // seconds) * seconds
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def aggregate_service_windows(
    session: Session,
    service_id: uuid.UUID,
    window_size_seconds: int,
) -> list[dict]:
    """
    Aggregate raw_logs into metric_windows for a given service and window size.
    Returns list of dicts ready for UPSERT.
    """
    result: list[dict] = []

    # Find the last closed window for this service
    watermark = session.execute(
        select(Watermark).where(
            Watermark.service_id == service_id,
            Watermark.window_size_seconds == window_size_seconds,
        )
    ).scalar_one_or_none()

    if watermark is None:
        # First run: find the earliest log and start from there
        earliest = session.execute(
            select(func.min(RawLog.timestamp)).where(RawLog.service_id == service_id)
        ).scalar()
        if earliest is None:
            return []
        last_closed = floor_dt(earliest, window_size_seconds)
    else:
        last_closed = floor_dt(
            watermark.last_closed_window_start,
            window_size_seconds,
        ) + timedelta(seconds=window_size_seconds)

    # Find last log timestamp for this service (ceiling cap)
    last_log_time = session.execute(
        select(func.max(RawLog.timestamp)).where(RawLog.service_id == service_id)
    ).scalar()
    if last_log_time is None:
        return []

    # Use an event-time watermark. A partially observed final window must not
    # be labeled as a traffic drop merely because no later event has arrived.
    event_watermark = _as_utc(last_log_time) - timedelta(minutes=GRACE_MINUTES)
    effective_end = floor_dt(event_watermark, window_size_seconds)

    # Get all logs in windows that are closed (past grace period) but not yet aggregated
    current_window = last_closed
    max_windows = 500  # safety cap
    win_count = 0
    while current_window < effective_end and win_count < max_windows:
        win_count += 1
        window_end = current_window + timedelta(seconds=window_size_seconds)

        metrics = _compute_metrics_for_window(session, service_id, current_window, window_end)

        # Compute baselines from previous 30 closed windows
        baselines = _compute_baselines(
            session,
            service_id,
            current_window,
            window_size_seconds,
            pending_windows=result,
        )

        # Merge metrics and baselines
        metrics.update(baselines)
        metrics["window_start"] = current_window
        metrics["closed_at"] = window_end + timedelta(minutes=GRACE_MINUTES)

        result.append(metrics)
        current_window = window_end

    # UPSERT watermark
    if result:
        new_watermark = result[-1]["window_start"]
        if watermark:
            watermark.last_closed_window_start = new_watermark
        elif not _is_postgres(session):
            session.add(
                Watermark(
                    service_id=service_id,
                    window_size_seconds=window_size_seconds,
                    last_closed_window_start=new_watermark,
                )
            )
        else:
            stmt = pg_insert(Watermark).values(
                service_id=service_id,
                window_size_seconds=window_size_seconds,
                last_closed_window_start=new_watermark,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["service_id", "window_size_seconds"],
                set_={"last_closed_window_start": stmt.excluded.last_closed_window_start},
            )
            session.execute(stmt)

    return result


def _compute_metrics_for_window(
    session: Session,
    service_id: uuid.UUID,
    window_start: datetime,
    window_end: datetime,
) -> dict:
    """Compute metrics from raw_logs within a time window."""
    # Count requests (rows with a request_id)
    request_count = (
        session.execute(
            select(func.count(RawLog.id)).where(
                RawLog.service_id == service_id,
                RawLog.timestamp >= window_start,
                RawLog.timestamp < window_end,
                RawLog.request_id.isnot(None),
            )
        ).scalar()
        or 0
    )

    # Count errors
    error_count = (
        session.execute(
            select(func.count(RawLog.id)).where(
                RawLog.service_id == service_id,
                RawLog.timestamp >= window_start,
                RawLog.timestamp < window_end,
                or_(
                    RawLog.level.in_(["ERROR", "CRITICAL"]),
                    RawLog.status_code >= 500,
                ),
            )
        ).scalar()
        or 0
    )

    # Error rate
    error_rate = (error_count / request_count) if request_count > 0 else None

    # Latency percentiles via raw SQL (SQLite for tests, PostgreSQL for production)
    latencies = (
        session.execute(
            select(RawLog.latency_ms).where(
                RawLog.service_id == service_id,
                RawLog.timestamp >= window_start,
                RawLog.timestamp < window_end,
                RawLog.latency_ms.isnot(None),
            )
        )
        .scalars()
        .all()
    )

    p50_latency = None
    p95_latency = None
    if latencies:
        arr = np.array(latencies)
        p50_latency = int(np.percentile(arr, 50))
        p95_latency = int(np.percentile(arr, 95))

    # Unique messages (cardinality proxy)
    unique_messages = (
        session.execute(
            select(func.count(func.distinct(RawLog.message))).where(
                RawLog.service_id == service_id,
                RawLog.timestamp >= window_start,
                RawLog.timestamp < window_end,
            )
        ).scalar()
        or 0
    )

    return {
        "request_count": request_count,
        "error_count": error_count,
        "error_rate": error_rate,
        "p50_latency_ms": p50_latency,
        "p95_latency_ms": p95_latency,
        "unique_messages": unique_messages,
    }


def _compute_baselines(
    session: Session,
    service_id: uuid.UUID,
    window_start: datetime,
    window_size_seconds: int,
    pending_windows: Sequence[dict] | None = None,
) -> dict:
    """Compute rolling median + MAD baselines from previous 30 closed windows."""
    pending = list(pending_windows or [])[-BASELINE_WINDOWS:]
    database_limit = max(0, BASELINE_WINDOWS - len(pending))
    prev_windows = (
        session.execute(
            select(MetricWindow)
            .where(
                MetricWindow.service_id == service_id,
                MetricWindow.window_size_seconds == window_size_seconds,
                MetricWindow.window_start < window_start,
            )
            .order_by(MetricWindow.window_start.desc())
            .limit(database_limit)
        )
        .scalars()
        .all()
        if database_limit
        else []
    )

    if len(prev_windows) + len(pending) < 3:
        # Not enough history for baseline
        return {
            "baseline_request_count_median": None,
            "baseline_request_count_mad": None,
            "baseline_error_rate_median": None,
            "baseline_error_rate_mad": None,
            "baseline_p95_latency_median": None,
            "baseline_p95_latency_mad": None,
        }

    def _median_mad(
        values: Sequence[float | int | None], floor: float = 0.0
    ) -> tuple[Optional[float], Optional[float]]:
        arr = np.array([v for v in values if v is not None], dtype=float)
        if len(arr) == 0:
            return None, None
        median = float(np.median(arr))
        mad = float(np.median(np.abs(arr - median)))
        mad = max(mad, floor)
        return median, mad

    req_counts = [w.request_count for w in prev_windows] + [
        row.get("request_count") for row in pending
    ]
    err_rates = [
        float(w.error_rate) if w.error_rate is not None else None for w in prev_windows
    ] + [row.get("error_rate") for row in pending]
    p95_lats = [w.p95_latency_ms for w in prev_windows] + [
        row.get("p95_latency_ms") for row in pending
    ]

    rc_median, rc_mad = _median_mad(req_counts, settings.mad_floor_request_count)
    er_median, er_mad = _median_mad(err_rates, settings.mad_floor_error_rate)
    p95_median, p95_mad = _median_mad(p95_lats, settings.mad_floor_p95_latency)

    return {
        "baseline_request_count_median": rc_median,
        "baseline_request_count_mad": rc_mad,
        "baseline_error_rate_median": er_median,
        "baseline_error_rate_mad": er_mad,
        "baseline_p95_latency_median": p95_median,
        "baseline_p95_latency_mad": p95_mad,
    }


def upsert_metric_window(session: Session, row: dict) -> None:
    """UPSERT a metric window row (idempotent)."""
    values = {
        "service_id": row.get("service_id"),
        "window_start": row["window_start"],
        "window_size_seconds": row.get("window_size_seconds"),
        "request_count": row.get("request_count", 0),
        "error_count": row.get("error_count", 0),
        "error_rate": row.get("error_rate"),
        "p50_latency_ms": row.get("p50_latency_ms"),
        "p95_latency_ms": row.get("p95_latency_ms"),
        "unique_messages": row.get("unique_messages", 0),
        "baseline_request_count_median": row.get("baseline_request_count_median"),
        "baseline_request_count_mad": row.get("baseline_request_count_mad"),
        "baseline_error_rate_median": row.get("baseline_error_rate_median"),
        "baseline_error_rate_mad": row.get("baseline_error_rate_mad"),
        "baseline_p95_latency_median": row.get("baseline_p95_latency_median"),
        "baseline_p95_latency_mad": row.get("baseline_p95_latency_mad"),
        "closed_at": row.get("closed_at"),
    }

    if not _is_postgres(session):
        existing = session.execute(
            select(MetricWindow).where(
                MetricWindow.service_id == values["service_id"],
                MetricWindow.window_start == values["window_start"],
                MetricWindow.window_size_seconds == values["window_size_seconds"],
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(MetricWindow(**values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        return

    stmt = pg_insert(MetricWindow).values(
        **values,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_metric_window",
        set_={
            "request_count": stmt.excluded.request_count,
            "error_count": stmt.excluded.error_count,
            "error_rate": stmt.excluded.error_rate,
            "p50_latency_ms": stmt.excluded.p50_latency_ms,
            "p95_latency_ms": stmt.excluded.p95_latency_ms,
            "unique_messages": stmt.excluded.unique_messages,
            "baseline_request_count_median": stmt.excluded.baseline_request_count_median,
            "baseline_request_count_mad": stmt.excluded.baseline_request_count_mad,
            "baseline_error_rate_median": stmt.excluded.baseline_error_rate_median,
            "baseline_error_rate_mad": stmt.excluded.baseline_error_rate_mad,
            "baseline_p95_latency_median": stmt.excluded.baseline_p95_latency_median,
            "baseline_p95_latency_mad": stmt.excluded.baseline_p95_latency_mad,
            "closed_at": stmt.excluded.closed_at,
        },
    )
    session.execute(stmt)


def run_aggregation_all_services(session: Session) -> int:
    """
    Run aggregation for all services, both window sizes.
    Returns total number of windows computed.
    """
    services = session.execute(select(Service)).scalars().all()
    total_windows = 0

    for service in services:
        for window_size in WINDOW_SIZES:
            rows = aggregate_service_windows(session, service.id, window_size)
            for row in rows:
                row["service_id"] = service.id
                row["window_size_seconds"] = window_size
                upsert_metric_window(session, row)
                total_windows += 1

    session.commit()
    return total_windows
