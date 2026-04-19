"""FIFO-приоритизация по времени поступления."""
from datetime import datetime

from algorithms.base import AlgorithmConfig, IPrioritizer, t_rel_h


class FIFOPrioritizer(IPrioritizer):
    """Алгоритм FIFO."""

    def compute_priority(self, task, t: datetime, params: AlgorithmConfig) -> float:
        return -t_rel_h(task.arrived_at)

    def sort(self, queue: list, t: datetime, params: AlgorithmConfig) -> list:
        return sorted(queue, key=lambda j: self.compute_priority(j, t, params), reverse=True)
