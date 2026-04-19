"""Тесты алгоритма Aging."""
from datetime import datetime, timedelta

import pytest
from algorithms.aging import AgingPrioritizer
from algorithms.base import AlgorithmConfig
from tests.conftest import make_task


@pytest.fixture
def params():
    return AlgorithmConfig(
        priority_weights={"CITO": 1000, "план": 1},
        beta=0.05,
    )


def test_aging_longer_wait_higher_priority(params):
    """Плановое с большим временем ожидания имеет больший приоритет."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    long_wait  = make_task(urgency_class="план", arrived_at=now - timedelta(hours=1))
    short_wait = make_task(urgency_class="план", arrived_at=now - timedelta(minutes=5))
    algo = AgingPrioritizer()
    result = algo.sort([short_wait, long_wait], now, params)
    assert result[0].id == long_wait.id


def test_aging_priority_grows_with_time(params):
    """Приоритет линейно растёт со временем ожидания."""
    t0 = datetime(2025, 1, 1, 10, 0, 0)
    task = make_task(urgency_class="план", arrived_at=t0)
    algo = AgingPrioritizer()
    p0 = algo.compute_priority(task, t0, params)
    p1 = algo.compute_priority(task, t0 + timedelta(hours=1), params)
    p2 = algo.compute_priority(task, t0 + timedelta(hours=2), params)
    assert p1 > p0
    assert p2 > p1
    # Линейный рост: p2 - p0 ≈ 2 × (p1 - p0)
    assert abs((p2 - p0) - 2 * (p1 - p0)) < 1e-6


def test_aging_starvation_prevention(params):
    """
    Предотвращение голодания: плановое задание гарантированно накапливает
    любой порог за конечное время (линейный рост с β > 0).
    """
    t0 = datetime(2025, 1, 1, 10, 0, 0)
    task = make_task(urgency_class="план", arrived_at=t0)
    algo = AgingPrioritizer()
    threshold = 500.0
    # При β=0.05 ч⁻¹ и w_план=1 нужно ~9999 ч — но рост конечный
    t_needed = t0 + timedelta(hours=(threshold - 1) / params.beta)
    p = algo.compute_priority(task, t_needed, params)
    assert p >= threshold


def test_aging_cito_always_wins(params):
    """CITO с w=1000 всегда обгоняет плановое даже после длительного ожидания."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    plan_old  = make_task(urgency_class="план", arrived_at=now - timedelta(hours=100))
    cito_new  = make_task(urgency_class="CITO",  arrived_at=now)
    algo = AgingPrioritizer()
    result = algo.sort([plan_old, cito_new], now, params)
    # При β=0.05, wait=100ч: plan_prio = 1 + 0.05*100 = 6; CITO = 1000
    assert result[0].id == cito_new.id
