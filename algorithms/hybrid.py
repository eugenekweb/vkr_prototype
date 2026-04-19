"""Гибрид EDF и Aging: дедлайн плюс накопление ожидания для плановых задач."""
from datetime import datetime

from algorithms.base import AlgorithmConfig, IPrioritizer

_SECONDS_PER_HOUR = 3600.0


class HybridPrioritizer(IPrioritizer):
    """Гибридный алгоритм EDF + Aging."""

    def compute_priority(self, task, t: datetime, params: AlgorithmConfig) -> float:
        remaining_h = (task.deadline_target - t).total_seconds() / _SECONDS_PER_HOUR
        remaining_h = max(params.epsilon, remaining_h)

        if task.urgency_class == "CITO":
            aging_term = 0.0
        else:
            wait_h = (t - task.arrived_at).total_seconds() / _SECONDS_PER_HOUR
            aging_term = params.beta * wait_h

        return 1.0 / remaining_h + aging_term

    def sort(self, queue: list, t: datetime, params: AlgorithmConfig) -> list:
        return sorted(queue, key=lambda j: self.compute_priority(j, t, params), reverse=True)
