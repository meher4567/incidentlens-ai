import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    timestamp: datetime
    service: str = Field(min_length=1, max_length=255)
    level: str = Field(pattern="^(DEBUG|INFO|WARN|ERROR|CRITICAL)$")
    message: str
    request_id: Optional[uuid.UUID] = None
    trace_id: Optional[uuid.UUID] = None
    latency_ms: Optional[int] = Field(None, ge=0)
    status_code: Optional[int] = Field(None, ge=100, le=599)
    host: Optional[str] = None
    region: Optional[str] = None


class LogBatch(BaseModel):
    events: list[LogEntry] = Field(min_length=1, max_length=1000)


class LogError(BaseModel):
    index: int
    message: str


class LogBatchResponse(BaseModel):
    ingested: int
    errors: list[LogError] = Field(default_factory=list)


class LogQuery(BaseModel):
    service: Optional[str] = None
    level: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    trace_id: Optional[uuid.UUID] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
