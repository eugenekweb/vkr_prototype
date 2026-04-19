"""Тесты гибридного алгоритма."""
from datetime import datetime, timedelta

import pytest
from algorithms.base import AlgorithmConfig
from algorithms.hybrid import HybridPrioritizer
from tests.conftest import make_task


@pytest.fixture
def params():
    return AlgorithmConfig(beta=0.05, epsilon=1.0)


def test_hybrid_closer_deadline_higher_priority(params):
    """Задание ближе к дедлайну имеет больший приоритет (EDF-компонента)."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    urgent = make_task(arrived_at=now - timedelta(hours=1),
                       deadline_target=now + timedelta(hours=0.5))
    relaxed = make_task(arrived_at=now - timedelta(hours=1),
                        deadline_target=now + timedelta(hours=3))
    algo = HybridPrioritizer()
    result = algo.sort([relaxed, urgent], now, params)
    assert result[0].id == urgent.id


def test_hybrid_numerical_stability_at_epsilon(params):
    """Численная устойчивость при remaining ≤ ε — нет ZeroDivisionError."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    # Дедлайн совпадает с now → remaining = 0 → max(ε, 0) = ε
    at_deadline = make_task(arrived_at=now - timedelta(hours=2),
                            deadline_target=now)
    algo = HybridPrioritizer()
    prio = algo.compute_priority(at_deadline, now, params)
    # Не должно быть исключения; π = 1/ε + aging_term
    assert prio == pytest.approx(1.0 / params.epsilon + params.beta * 2.0, rel=1e-5)


def test_hybrid_cito_no_aging_term(params):
    """Для CITO-заданий aging_term = 0 при любом времени ожидания."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    cito = make_task(urgency_class="CITO",
                     arrived_at=now - timedelta(hours=10),
                     deadline_target=now + timedelta(hours=1))
    algo = HybridPrioritizer()
    prio = algo.compute_priority(cito, now, params)
    # aging_term = 0 для CITO; π = 1/remaining
    remaining_h = 1.0
    expected = 1.0 / remaining_h
    assert prio == pytest.approx(expected, rel=1e-5)


def test_hybrid_edf_dominates_near_deadline(params):
    """При приближении к дедлайну EDF-компонента резко растёт (гиперболически).
    Используем remaining > epsilon, чтобы max(ε, remaining) = remaining.
    ε=1.0 ч: p_far при 6 ч → 1/6≈0.167; p_near при 1.5 ч → 1/1.5≈0.667; ≥ 3x.
    """
    now = datetime(2025, 1, 1, 10, 0, 0)
    task = make_task(urgency_class="план",
                     arrived_at=now - timedelta(hours=1))
    algo = HybridPrioritizer()
    # Оба remaining > epsilon=1.0, чтобы гиперболический рост был виден
    task.deadline_target = now + timedelta(hours=6)    # remaining=6 > ε=1 → π≈0.17+0.05=0.22
    p_far = algo.compute_priority(task, now, params)
    task.deadline_target = now + timedelta(hours=1.5)  # remaining=1.5 > ε=1 → π≈0.67+0.05=0.72
    p_near = algo.compute_priority(task, now, params)
    assert p_near > p_far * 3  # гиперболический рост: 0.72 >> 0.22


def test_hybrid_plan_has_aging(params):
    """Плановое задание с большим ожиданием получает больший приоритет."""
    now = datetime(2025, 1, 1, 10, 0, 0)
    wait_short = make_task(urgency_class="план",
                           arrived_at=now - timedelta(minutes=10),
                           deadline_target=now + timedelta(hours=2))
    wait_long  = make_task(urgency_class="план",
                           arrived_at=now - timedelta(hours=2),
                           deadline_target=now + timedelta(hours=2))
    algo = HybridPrioritizer()
    p_short = algo.compute_priority(wait_short, now, params)
    p_long  = algo.compute_priority(wait_long,  now, params)
    assert p_long > p_short
