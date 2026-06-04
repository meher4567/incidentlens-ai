import uuid
from datetime import datetime

from pydantic import BaseModel


class AnomalyResponse(BaseModel):
    id: int
    service_id: uuid.UUID
    metric: str
    window_start: datetime
    window_size_seconds: int
    detector: str
    score: float
    observed_value: float
    baseline_value: float
    severity: str
    created_at: datetime

    model_config = {"from_attributes": True}
