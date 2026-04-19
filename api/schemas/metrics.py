"""Pydantic-схемы для метрик."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MetricsResponse(BaseModel):
    """Снимок операционных метрик."""
    SLA_CITO_target: float
    SLA_plan_target: float
    SLA_plan_max: float
    load_variance: float
    queue_depth: int
    queue_by_modality: dict[str, int]
    doctors_load: list[dict]
    timestamp: datetime
