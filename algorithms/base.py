"""Базовый интерфейс и общие параметры алгоритмов приоритизации."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

_ALGO_BASE_DT = datetime(2025, 1, 1, 0, 0, 0)
_SECONDS_PER_HOUR = 3600.0


def t_rel_h(dt: datetime, base: datetime = _ALGO_BASE_DT) -> float:
    """Переводит datetime в часы относительно базовой точки."""
    if dt.tzinfo is not None and base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    elif dt.tzinfo is None and base.tzinfo is not None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - base).total_seconds() / _SECONDS_PER_HOUR


@dataclass
class AlgorithmConfig:
    """Параметры алгоритма из config.yaml."""
    type: str = "EDF"
    beta: float = 0.05
    delta: float = 1.0e-6
    epsilon: float = 1.0
    priority_weights: dict = field(default_factory=lambda: {"CITO": 1000, "план": 1})

    @classmethod
    def from_dict(cls, data: dict) -> "AlgorithmConfig":
        return cls(
            type=data.get("type", "EDF"),
            beta=float(data.get("beta", 0.05)),
            delta=float(data.get("delta", 1e-6)),
            epsilon=float(data.get("epsilon", 1.0)),
            priority_weights=data.get("priority_weights", {"CITO": 1000, "план": 1}),
        )

    def urgency_weight(self, urgency_class: str) -> float:
        """Возвращает вес срочности."""
        return float(self.priority_weights.get(urgency_class, 1))


class IPrioritizer(ABC):
    """Абстрактный базовый класс алгоритма приоритизации."""

    @abstractmethod
    def sort(
        self,
        queue: list,
        t: datetime,
        params: AlgorithmConfig,
    ) -> list:
        """Возвращает задания, упорядоченные по убыванию приоритета."""

    @abstractmethod
    def compute_priority(
        self,
        task,
        t: datetime,
        params: AlgorithmConfig,
    ) -> float:
        """Вычисляет приоритет одного задания."""
