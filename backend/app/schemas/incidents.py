import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TimelineEvent(BaseModel):
    alert_id: uuid.UUID
    service_name: str
    anomaly_type: str
    start_window: datetime
    severity: str
    trace_id: Optional[uuid.UUID] = None
    upstream_of: list[str] = Field(default_factory=list)
    downstream_of: list[str] = Field(default_factory=list)


class RootCauseScoreResponse(BaseModel):
    service_id: uuid.UUID
    service_name: str
    score: float
    rank: int
    feature_vector: Optional[dict] = None
    feature_contributions: Optional[dict] = None

    model_config = {"from_attributes": True}


class IncidentResponse(BaseModel):
    id: uuid.UUID
    start_time: datetime
    end_time: Optional[datetime] = None
    severity: str
    affected_services: list[uuid.UUID]
    affected_service_names: list[str] = Field(default_factory=list)
    alert_count: int = 0
    closed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class IncidentDetailResponse(IncidentResponse):
    alerts: list[dict] = Field(default_factory=list)
    root_cause_scores: list[RootCauseScoreResponse] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
