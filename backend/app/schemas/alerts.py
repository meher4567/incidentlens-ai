import uuid
from datetime import datetime

from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    anomaly_type: str
    start_window: datetime
    end_window: datetime
    severity: str
    observed_value: float
    baseline_value: float
    anomaly_ids: list[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class DeduplicatedAlertResponse(BaseModel):
    canonical_alert_id: uuid.UUID
    duplicate_alert_id: uuid.UUID
    dedupe_reason: str
    created_at: datetime

    model_config = {"from_attributes": True}
