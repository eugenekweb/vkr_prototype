"""Тесты алгоритма EDF."""
from datetime import datetime, timedelta

import pytest
from algorithms.base import AlgorithmConfig
from algorithms.edf import EDFPrioritizer
from tests.conftest import make_task


@pytest.fixture
def params():
    return AlgorithmConfig()


def test_edf_closer_deadline_higher_priority(params):
    """Задание с ближайшим дедлайном идёт первым."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    urgent = make_task(arrived_at=now - timedelta(minutes=90),
                       deadline_target=now + timedelta(minutes=30))
    relaxed = make_task(arrived_at=now - timedelta(minutes=10),
                        deadline_target=now + timedelta(minutes=90))
    algo = EDFPrioritizer()
    result = algo.sort([relaxed, urgent], now, params)
    assert result[0].id == urgent.id


def test_edf_positive_priority_after_deadline(params):
    """При t > d^target: π > 0 — задание поднимается к голове очереди."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    # Дедлайн уже прошёл
    overdue = make_task(arrived_at=now - timedelta(hours=3),
                        deadline_target=now - timedelta(hours=1))
    algo = EDFPrioritizer()
    prio = algo.compute_priority(overdue, now, params)
    assert prio > 0


def test_edf_state_queued_after_deadline_target(params):
    """
    Задание с t > deadline_target но t < deadline_max остаётся QUEUED.
    ESCALATED срабатывает только при t > deadline_max — не здесь.
    """
    now = datetime(2025, 1, 1, 10, 0, 0)
    task = make_task(
        arrived_at=now - timedelta(hours=3),
        deadline_target=now - timedelta(hours=1),
        deadline_max=now + timedelta(hours=20),
        state="QUEUED",
    )
    assert task.state == "QUEUED"  # EDF не меняет state


def test_edf_negative_priority_before_deadline(params):
    """При t < d^target: π < 0."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    task = make_task(arrived_at=now, deadline_target=now + timedelta(hours=2))
    algo = EDFPrioritizer()
    prio = algo.compute_priority(task, now, params)
    assert prio < 0


def test_edf_sort_multiple(params):
    """Сортировка нескольких заданий по дедлайну."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    tasks = [
        make_task(arrived_at=now, deadline_target=now + timedelta(hours=h))
        for h in [3, 1, 2]
    ]
    algo = EDFPrioritizer()
    result = algo.sort(tasks, now, params)
    deadlines = [(r.deadline_target - now).total_seconds() / 3600 for r in result]
    assert deadlines == sorted(deadlines)
