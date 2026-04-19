"""Aging-приоритизация: приоритет растёт с временем ожидания."""
from datetime import datetime

from algorithms.base import AlgorithmConfig, IPrioritizer

_SECONDS_PER_HOUR = 3600.0


class AgingPrioritizer(IPrioritizer):
    """Алгоритм Aging."""

    def compute_priority(self, task, t: datetime, params: AlgorithmConfig) -> float:
        wait_h = (t - task.arrived_at).total_seconds() / _SECONDS_PER_HOUR
        w = params.urgency_weight(task.urgency_class)
        return w + params.beta * wait_h

    def sort(self, queue: list, t: datetime, params: AlgorithmConfig) -> list:
        return sorted(queue, key=lambda j: self.compute_priority(j, t, params), reverse=True)
