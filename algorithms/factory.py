"""Фабрика экземпляров приоритизаторов по имени алгоритма."""
from __future__ import annotations

from algorithms.aging import AgingPrioritizer
from algorithms.base import AlgorithmConfig, IPrioritizer
from algorithms.edf import EDFPrioritizer
from algorithms.fifo import FIFOPrioritizer
from algorithms.hybrid import HybridPrioritizer
from algorithms.priority_queue import PriorityQueuePrioritizer

_REGISTRY: dict[str, type[IPrioritizer]] = {
    "FIFO": FIFOPrioritizer,
    "PQ": PriorityQueuePrioritizer,
    "AGING": AgingPrioritizer,
    "EDF": EDFPrioritizer,
    "HYBRID": HybridPrioritizer,
}


class PrioritizerFactory:
    @staticmethod
    def create(algorithm_type: str, params: AlgorithmConfig | None = None) -> IPrioritizer:
        """
        Создаёт экземпляр IPrioritizer по типу алгоритма.
        Raises ValueError для неизвестного типа.

        Параметры передаются в sort()/compute_priority() при каждом вызове.
        """
        cls = _REGISTRY.get(algorithm_type.upper())
        if cls is None:
            raise ValueError(
                f"Неизвестный алгоритм: '{algorithm_type}'. "
                f"Допустимые значения: {list(_REGISTRY.keys())}"
            )
        return cls()

    @staticmethod
    def available_algorithms() -> list[str]:
        return list(_REGISTRY.keys())
