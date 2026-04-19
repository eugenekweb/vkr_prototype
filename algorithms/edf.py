"""EDF-приоритизация по ближайшему целевому дедлайну."""
from datetime import datetime

from algorithms.base import AlgorithmConfig, IPrioritizer, t_rel_h


class EDFPrioritizer(IPrioritizer):
    """Алгоритм наименьшего дедлайна."""

    def compute_priority(self, task, t: datetime, params: AlgorithmConfig) -> float:
        return t_rel_h(t) - t_rel_h(task.deadline_target)

    def sort(self, queue: list, t: datetime, params: AlgorithmConfig) -> list:
        return sorted(queue, key=lambda j: self.compute_priority(j, t, params), reverse=True)
