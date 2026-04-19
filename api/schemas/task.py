"""Pydantic-схемы для заданий."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TaskCreateRequest(BaseModel):
    """Запрос на создание задания."""
    external_id: str = Field(..., description="Идентификатор исследования в МИС")
    modality: str = Field(..., description="Модальность m(j) ∈ M")
    urgency_class: str = Field(..., description="Класс срочности: CITO или план")
    complexity: float = Field(1.0, gt=0, description="Коэффициент трудоёмкости s(j)")

    model_config = {"json_schema_extra": {
        "example": {
            "external_id": "ris-study-20250315-00441",
            "modality": "ECG_REST",
            "urgency_class": "план",
            "complexity": 1.0,
        }
    }}


class TaskResponse(BaseModel):
    """Данные задания."""
    id: uuid.UUID
    external_id: str
    modality: str
    urgency_class: str
    complexity: float
    arrived_at: datetime
    deadline_target: datetime
    deadline_max: datetime
    state: str
    assigned_to: Optional[uuid.UUID]
    started_at: Optional[datetime]
    done_at: Optional[datetime]
    escalated_at: Optional[datetime]
    estimated_tat_h: Optional[float] = None

    model_config = {"from_attributes": True}


class TaskStatusUpdateRequest(BaseModel):
    """Запрос на смену состояния задания."""
    state: str = Field(..., description="Новое состояние: IN_PROGRESS или DONE")
    doctor_id: Optional[uuid.UUID] = None


class AuditEventResponse(BaseModel):
    """Событие журнала."""
    id: uuid.UUID
    event_type: str
    task_id: Optional[uuid.UUID]
    actor: str
    timestamp: datetime
    algorithm_used: Optional[str]
    queue_depth: Optional[int]
    payload_json: Optional[dict]

    model_config = {"from_attributes": True}
