"""Дополнительные тесты для MetricsCollector."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.metrics_collector import MetricsCollector, MetricsSnapshot
from tests.conftest import make_doctor, make_task


@pytest.mark.unit
@pytest.mark.core
def test_record_queue_length_same_timestamp_overwrites_last_value():
    """Если timestamp совпадает, последнее значение должно перезаписать предыдущее."""
    mc = MetricsCollector()
    mc.record_queue_length(5.0, 3)
    mc.record_queue_length(5.0, 7)

    metrics = mc.compute_queue_metrics(warmup_time_min=0.0, end_min=10.0)
    assert metrics["max_queue_length"] == 7


@pytest.mark.unit
@pytest.mark.core
def test_weighted_queue_metrics_empty_timeline():
    """Пустая timeline возвращает нули."""
    avg, peak, p95 = MetricsCollector._weighted_queue_metrics([], 0.0, 10.0)
    assert avg == 0.0
    assert peak == 0
    assert p95 == 0.0


@pytest.mark.unit
@pytest.mark.core
def test_weighted_queue_metrics_invalid_interval():
    """Невалидный интервал возвращает нули."""
    timeline = [(0.0, 3), (5.0, 1)]
    avg, peak, p95 = MetricsCollector._weighted_queue_metrics(timeline, 10.0, 5.0)
    assert avg == 0.0
    assert peak == 0
    assert p95 == 0.0


@pytest.mark.unit
@pytest.mark.core
def test_compute_final_variance_with_completed_tasks():
    """compute_final_variance() учитывает завершённые задания по врачам."""
    mc = MetricsCollector()
    d1 = make_doctor(productivity_rate=1.0)
    d2 = make_doctor(productivity_rate=1.0)

    t1 = make_task(complexity=2.0)
    t1.assigned_to = d1.id
    t2 = make_task(complexity=4.0)
    t2.assigned_to = d2.id
    mc.record_completed(t1)
    mc.record_completed(t2)

    variance = mc.compute_final_variance([d1, d2], period_hours=2.0)
    assert variance > 0.0


@pytest.mark.unit
@pytest.mark.core
def test_compute_final_variance_no_doctors_or_zero_period():
    """Граничные случаи compute_final_variance() дают 0."""
    mc = MetricsCollector()
    assert mc.compute_final_variance([], period_hours=8.0) == 0.0
    assert mc.compute_final_variance([make_doctor()], period_hours=0.0) == 0.0


@pytest.mark.unit
@pytest.mark.core
def test_compute_load_variance_handles_zero_productivity():
    """Нулевая производительность не должна ломать compute_load_variance()."""
    mc = MetricsCollector()
    d = make_doctor(productivity_rate=0.0, current_load=5.0)
    assert mc.compute_load_variance([d], period_hours=8.0) == 0.0


@pytest.mark.unit
@pytest.mark.core
def test_sla_warning_with_doctors_and_publish_error(monkeypatch):
    """check_sla_violations() использует estimate_tat и переживает ошибки обработчиков."""
    mc = MetricsCollector(target_hours=2.0, max_hours=24.0, warning_threshold=0.5)
    now = datetime.now(timezone.utc)
    task = make_task(
        arrived_at=now - timedelta(minutes=30),
        deadline_target=now + timedelta(hours=1),
        deadline_max=now + timedelta(hours=24),
        state="QUEUED",
    )
    doctor = make_doctor(specializations=["ECG_REST"], productivity_rate=1.0)

    def bad_handler(**kwargs):
        raise RuntimeError("boom")

    mc.subscribe("SLA_WARNING", bad_handler)

    events = mc.check_sla_violations(now, [task], doctors=[doctor])
    assert any(event["type"] == "SLA_WARNING" for event in events)


@pytest.mark.unit
@pytest.mark.core
def test_sla_violation_event_contains_expected_fields():
    """SLA_VIOLATION должен включать диагностические поля."""
    mc = MetricsCollector(target_hours=2.0, max_hours=24.0, warning_threshold=0.5)
    now = datetime.now(timezone.utc)
    task = make_task(
        arrived_at=now - timedelta(hours=25),
        deadline_target=now - timedelta(hours=2),
        deadline_max=now - timedelta(hours=1),
        state="QUEUED",
    )
    events = mc.check_sla_violations(now, [task])
    violation = next(e for e in events if e["type"] == "SLA_VIOLATION")
    assert violation["task_id"] == task.id
    assert "deadline_exceeded_by_h" in violation
    assert violation["current_state"] == "QUEUED"


@pytest.mark.unit
@pytest.mark.core
def test_get_metrics_snapshot_structure():
    """get_metrics() возвращает заполненный MetricsSnapshot."""
    mc = MetricsCollector()
    d = make_doctor(productivity_rate=2.0, current_load=4.0)
    t = make_task(modality="EEG")
    snap = mc.get_metrics([t], [d])

    assert isinstance(snap, MetricsSnapshot)
    assert snap.queue_depth == 1
    assert snap.queue_by_modality == {"EEG": 1}
    assert len(snap.doctors_load) == 1


@pytest.mark.unit
@pytest.mark.core
def test_get_metrics_uses_final_variance_when_completed_tasks_exist():
    """Если есть завершённые задания, load_variance берётся из final variance."""
    mc = MetricsCollector()
    d = make_doctor(productivity_rate=1.0)
    t = make_task(complexity=2.0)
    t.assigned_to = d.id
    mc.record_completed(t)

    snap = mc.get_metrics([], [d])
    assert snap.load_variance == snap.sigma_w2_final


@pytest.mark.unit
@pytest.mark.core
def test_compute_sla_metrics_no_tasks_defaults_to_one():
    """Без данных SLA метрики по умолчанию равны 1.0."""
    mc = MetricsCollector()
    sla = mc.compute_sla_metrics()
    assert sla["SLA_plan_target"] == 1.0
    assert sla["SLA_plan_max"] == 1.0
    assert sla["SLA_CITO_target"] == 1.0
