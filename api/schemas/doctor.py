"""Pydantic-схемы для врачей."""
from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class DoctorResponse(BaseModel):
    id: uuid.UUID
    specializations: list[str]
    productivity_rate: float
    is_available: bool
    current_load: float
    normalized_load: Optional[float] = None

    model_config = {"from_attributes": True}


class DoctorAvailabilityRequest(BaseModel):
    is_available: bool
