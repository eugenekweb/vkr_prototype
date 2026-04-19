"""Тесты алгоритма Priority Queue."""
from datetime import datetime, timedelta

import pytest
from algorithms.base import AlgorithmConfig
from algorithms.priority_queue import PriorityQueuePrioritizer
from tests.conftest import make_task


@pytest.fixture
def params():
    return AlgorithmConfig(
        priority_weights={"CITO": 1000, "план": 1},
        delta=1e-6,
    )


def test_cito_always_first(params):
    """CITO-задание всегда первое независимо от времени поступления."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    plan_early = make_task(urgency_class="план", arrived_at=now - timedelta(hours=5))
    cito_late  = make_task(urgency_class="CITO",  arrived_at=now - timedelta(minutes=1))
    algo = PriorityQueuePrioritizer()
    result = algo.sort([plan_early, cito_late], now, params)
    assert result[0].id == cito_late.id


def test_two_cito_fifo_order(params):
    """Два CITO — поступившее раньше идёт первым (δ обеспечивает FIFO)."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    cito1 = make_task(urgency_class="CITO", arrived_at=now - timedelta(minutes=10))
    cito2 = make_task(urgency_class="CITO", arrived_at=now - timedelta(minutes=5))
    algo = PriorityQueuePrioritizer()
    result = algo.sort([cito2, cito1], now, params)
    assert result[0].id == cito1.id


def test_two_plan_fifo_order(params):
    """Два плановых — δ обеспечивает FIFO внутри класса."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    p1 = make_task(urgency_class="план", arrived_at=now - timedelta(minutes=20))
    p2 = make_task(urgency_class="план", arrived_at=now - timedelta(minutes=10))
    algo = PriorityQueuePrioritizer()
    result = algo.sort([p2, p1], now, params)
    assert result[0].id == p1.id


def test_delta_does_not_invert_urgency(params):
    """δ не нарушает порядок между классами срочности."""
    # CITO w=1000, план w=1; даже при большом t_arr δ не перекрывает разрыв
    now = datetime(2025, 1, 1, 10, 0, 0)
    plan = make_task(urgency_class="план", arrived_at=now - timedelta(days=365))
    cito = make_task(urgency_class="CITO",  arrived_at=now)
    algo = PriorityQueuePrioritizer()
    result = algo.sort([plan, cito], now, params)
    assert result[0].id == cito.id
