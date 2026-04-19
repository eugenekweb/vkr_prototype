"""Тесты алгоритма FIFO."""
from datetime import datetime, timedelta, timezone

import pytest
from algorithms.base import AlgorithmConfig
from algorithms.fifo import FIFOPrioritizer
from tests.conftest import make_task


@pytest.fixture
def params():
    return AlgorithmConfig(priority_weights={"CITO": 1000, "план": 1})


def test_fifo_order_by_arrived_at(params):
    """Задание с наименьшим t_arr имеет наибольший приоритет."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    early = make_task(arrived_at=now - timedelta(minutes=30))
    mid   = make_task(arrived_at=now - timedelta(minutes=15))
    late  = make_task(arrived_at=now)
    algo = FIFOPrioritizer()
    result = algo.sort([late, early, mid], now, params)
    assert result[0].id == early.id
    assert result[1].id == mid.id
    assert result[2].id == late.id


def test_fifo_single_task(params):
    """Один элемент — возвращается как есть."""
    task = make_task()
    algo = FIFOPrioritizer()
    result = algo.sort([task], datetime.now(timezone.utc), params)
    assert len(result) == 1
    assert result[0].id == task.id


def test_fifo_no_urgency_influence(params):
    """FIFO игнорирует urgency_class — только время поступления."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    cito = make_task(urgency_class="CITO",  arrived_at=now - timedelta(minutes=5))
    plan = make_task(urgency_class="план", arrived_at=now - timedelta(minutes=10))
    algo = FIFOPrioritizer()
    result = algo.sort([cito, plan], now, params)
    # Плановое пришло раньше — FIFO должен поставить его первым
    assert result[0].id == plan.id


def test_fifo_compute_priority(params):
    """compute_priority = -t_rel_h(arrived_at); использует относительное время."""
    from algorithms.base import _ALGO_BASE_DT, t_rel_h
    now = datetime(2025, 1, 1, 10, 0, 0)
    task = make_task(arrived_at=now)
    algo = FIFOPrioritizer()
    prio = algo.compute_priority(task, now, params)
    assert prio == pytest.approx(-t_rel_h(now))
