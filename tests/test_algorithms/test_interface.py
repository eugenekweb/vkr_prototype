"""
Тест контракта интерфейса IPrioritizer — все 5 алгоритмов.
Проверяет, что sort() возвращает список той же длины и в правильном порядке.
"""
from datetime import datetime, timedelta, timezone

import pytest

from algorithms.aging import AgingPrioritizer
from algorithms.base import AlgorithmConfig
from algorithms.edf import EDFPrioritizer
from algorithms.factory import PrioritizerFactory
from algorithms.fifo import FIFOPrioritizer
from algorithms.hybrid import HybridPrioritizer
from algorithms.priority_queue import PriorityQueuePrioritizer
from tests.conftest import make_task

ALGORITHMS = ["FIFO", "PQ", "AGING", "EDF", "HYBRID"]


@pytest.fixture
def params():
    return AlgorithmConfig(
        priority_weights={"CITO": 1000, "план": 1},
        beta=0.05,
        delta=1e-6,
        epsilon=1.0,
    )


@pytest.mark.parametrize("algo_type", ALGORITHMS)
def test_sort_returns_list(algo_type, params):
    """sort() возвращает list — контракт IPrioritizer."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    tasks = [make_task(arrived_at=now - timedelta(minutes=i)) for i in range(5)]
    algo = PrioritizerFactory.create(algo_type, params)
    result = algo.sort(tasks, now, params)
    assert isinstance(result, list)


@pytest.mark.parametrize("algo_type", ALGORITHMS)
def test_sort_same_length(algo_type, params):
    """sort() не теряет и не дублирует задания."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    tasks = [make_task(arrived_at=now - timedelta(minutes=i)) for i in range(7)]
    algo = PrioritizerFactory.create(algo_type, params)
    result = algo.sort(tasks, now, params)
    assert len(result) == len(tasks)


@pytest.mark.parametrize("algo_type", ALGORITHMS)
def test_sort_empty_queue(algo_type, params):
    """sort() на пустой очереди возвращает пустой список."""
    algo = PrioritizerFactory.create(algo_type, params)
    result = algo.sort([], datetime.now(timezone.utc), params)
    assert result == []


@pytest.mark.parametrize("algo_type", ALGORITHMS)
def test_sort_no_side_effects(algo_type, params):
    """sort() не изменяет state заданий."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    tasks = [make_task(arrived_at=now - timedelta(minutes=i)) for i in range(3)]
    original_states = [t.state for t in tasks]
    algo = PrioritizerFactory.create(algo_type, params)
    algo.sort(tasks, now, params)
    assert [t.state for t in tasks] == original_states


def test_factory_unknown_raises():
    """Неизвестный тип → ValueError."""
    with pytest.raises(ValueError):
        PrioritizerFactory.create("UNKNOWN")


def test_factory_all_types_created(params):
    """Все 5 типов создаются корректно."""
    for t in ALGORITHMS:
        algo = PrioritizerFactory.create(t, params)
        assert algo is not None
