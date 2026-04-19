"""Pydantic-схемы для конфигурации алгоритма."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AlgorithmConfigRequest(BaseModel):
    """Запрос на изменение параметров алгоритма."""
    type: str = Field(..., description="Тип алгоритма: FIFO | PQ | AGING | EDF | HYBRID")
    beta: Optional[float] = Field(None, description="Коэффициент накопления")
    delta: Optional[float] = Field(None, description="Коэффициент очереди по приоритету")
    epsilon: Optional[float] = Field(None, description="Порог переключения для Hybrid")
    priority_weights: Optional[dict[str, float]] = Field(
        None, description="Веса срочности"
    )

    model_config = {"json_schema_extra": {
        "example": {
            "type": "HYBRID",
            "beta": 0.05,
            "epsilon": 1.0,
        }
    }}


class AlgorithmConfigResponse(BaseModel):
    type: str
    beta: float
    delta: float
    epsilon: float
    priority_weights: dict[str, float]
