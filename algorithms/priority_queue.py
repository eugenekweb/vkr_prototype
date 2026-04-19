"""Приоритизация с весами срочности и штрафом за давность поступления."""
from datetime import datetime

from algorithms.base import AlgorithmConfig, IPrioritizer, t_rel_h


class PriorityQueuePrioritizer(IPrioritizer):
    """Алгоритм приоритизации Priority Queue."""

    def compute_priority(self, task, t: datetime, params: AlgorithmConfig) -> float:
        w = params.urgency_weight(task.urgency_class)
        return w - params.delta * t_rel_h(task.arrived_at)

    def sort(self, queue: list, t: datetime, params: AlgorithmConfig) -> list:
        return sorted(queue, key=lambda j: self.compute_priority(j, t, params), reverse=True)
