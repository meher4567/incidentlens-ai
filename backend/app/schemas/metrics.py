import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MetricWindowResponse(BaseModel):
    id: int
    service_id: uuid.UUID
    window_start: datetime
    window_size_seconds: int
    request_count: int
    error_count: int
    error_rate: Optional[float] = None
    p50_latency_ms: Optional[int] = None
    p95_latency_ms: Optional[int] = None
    unique_messages: int
    baseline_request_count_median: Optional[float] = None
    baseline_request_count_mad: Optional[float] = None
    baseline_error_rate_median: Optional[float] = None
    baseline_error_rate_mad: Optional[float] = None
    baseline_p95_latency_median: Optional[float] = None
    baseline_p95_latency_mad: Optional[float] = None
    closed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ServiceHealthResponse(BaseModel):
    service_id: uuid.UUID
    service_name: str
    windows: list[MetricWindowResponse]
    window_size_seconds: int
