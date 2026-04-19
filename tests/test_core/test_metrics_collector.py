"""Тесты MetricsCollector."""
from datetime import datetime, timedelta, timezone

import pytest
from core.metrics_collector import MetricsCollector
from tests.conftest import make_doctor, make_task


@pytest.fixture
def mc():
    return MetricsCollector(
        target_hours=2.0, max_hours=24.0, warning_threshold=0.5
    )


def test_sla_warning_at_50_percent(mc):
    """SLA_WARNING при elapsed ≥ 50% Δ^target."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    # Задание ждёт 1.0 ч (50% от 2 ч)
    task = make_task(
        arrived_at=now - timedelta(hours=1.0),
        deadline_target=now + timedelta(hours=1.0),
        deadline_max=now + timedelta(hours=22),
        state="QUEUED",
    )
    events = mc.check_sla_violations(now, [task])
    warning_events = [e for e in events if e["type"] == "SLA_WARNING"]
    assert len(warning_events) == 1


def test_sla_violation_after_max(mc):
    """SLA_VIOLATION при t > d^max."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    task = make_task(
        arrived_at=now - timedelta(hours=25),
        deadline_target=now - timedelta(hours=23),
        deadline_max=now - timedelta(hours=1),  # предельный срок уже прошёл
        state="QUEUED",
    )
    events = mc.check_sla_violations(now, [task])
    violation_events = [e for e in events if e["type"] == "SLA_VIOLATION"]
    assert len(violation_events) == 1


def test_load_variance_zero_equal_loads(mc):
    """σ²_W = 0 при одинаковой нормированной нагрузке."""
    d1 = make_doctor(productivity_rate=1.0, current_load=2.0)
    d2 = make_doctor(productivity_rate=1.0, current_load=2.0)
    variance = mc.compute_load_variance([d1, d2], period_hours=1.0)
    assert variance == pytest.approx(0.0, abs=1e-9)


def test_load_variance_nonzero_different_loads(mc):
    """σ²_W > 0 при разной нагрузке."""
    d1 = make_doctor(productivity_rate=1.0, current_load=4.0)
    d2 = make_doctor(productivity_rate=1.0, current_load=0.0)
    variance = mc.compute_load_variance([d1, d2], period_hours=1.0)
    assert variance > 0.0


def test_sla_plan_target(mc):
    """SLA_plan_target: доля плановых с TAT ≤ 2 ч."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    # Выполнено в срок
    t1 = make_task(urgency_class="план",
                   arrived_at=now - timedelta(hours=1))
    t1.done_at = now  # TAT = 1 ч ≤ 2 ч
    # Выполнено с опозданием
    t2 = make_task(urgency_class="план",
                   arrived_at=now - timedelta(hours=3))
    t2.done_at = now  # TAT = 3 ч > 2 ч
    mc.record_completed(t1)
    mc.record_completed(t2)
    sla = mc.compute_sla_metrics()
    assert sla["SLA_plan_target"] == pytest.approx(0.5)


def test_observer_subscription():
    """subscribe/publish: обработчик вызывается при событии."""
    mc_obj = MetricsCollector()
    received = []
    mc_obj.subscribe("SLA_WARNING", lambda **kw: received.append(kw))
    mc_obj.publish("SLA_WARNING", task=None, t=datetime.now(timezone.utc))
    assert len(received) == 1
