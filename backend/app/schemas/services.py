import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ServiceResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DependencyCreate(BaseModel):
    upstream: str = Field(min_length=1, max_length=255)
    downstream: str = Field(min_length=1, max_length=255)


class DependencyResponse(BaseModel):
    upstream_id: uuid.UUID
    downstream_id: uuid.UUID
    upstream_name: Optional[str] = None
    downstream_name: Optional[str] = None
