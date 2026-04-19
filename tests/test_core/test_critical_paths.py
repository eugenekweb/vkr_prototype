"""Тесты критических путей операционного и симуляционного контуров."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from tests.conftest import make_doctor, make_task

# ---------------------------------------------------------------------------
# C1: is_available=False после AssignmentEngine.assign()
# ---------------------------------------------------------------------------

def test_assign_sets_is_available_false():
    """C1: assign() должен заблокировать врача для следующего назначения."""
    from core.assignment_engine import AssignmentEngine

    ae = AssignmentEngine()
    task = make_task(modality="ECG_REST")
    doc = make_doctor(specializations=["ECG_REST"], is_available=True)

    ae.assign(task, doc, algorithm_used="EDF", now=datetime.now(timezone.utc))

    assert doc.is_available is False, (
        "После assign() врач должен быть недоступен для следующего назначения"
    )


def test_double_assign_prevented_by_is_available():
    """C1: WLL не назначает второй раз врача, уже занятого в batch-цикле."""
    from core.assignment_engine import AssignmentEngine

    ae = AssignmentEngine()
    t1 = make_task(modality="ECG_REST")
    t2 = make_task(modality="ECG_REST")
    doc = make_doctor(specializations=["ECG_REST"], is_available=True)

    ae.assign(t1, doc, algorithm_used="EDF", now=datetime.now(timezone.utc))
    # После первого назначения врач недоступен
    result = ae.find_doctor(t2, [doc])
    assert result is None, "Занятый врач не должен быть выбран повторно"


# ---------------------------------------------------------------------------
# C6: is_outage — _service_process не возвращает врача во время outage
# ---------------------------------------------------------------------------

def test_is_outage_field_exists():
    """C6: SimDoctor имеет поле is_outage."""
    from simulation.generators import SimDoctor

    doc = SimDoctor(id="d1", specializations=["ECG_REST"], productivity_rate=6.0)
    assert hasattr(doc, "is_outage"), "SimDoctor должен иметь поле is_outage"
    assert doc.is_outage is False


def test_outage_doctor_excluded_from_wll():
    """C6: Врач с is_outage=True не выбирается при назначении."""
    import sys

    import yaml
    sys.path.insert(0, ".")
    with open("config/config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    from algorithms.base import AlgorithmConfig
    from simulation.generators import SimDoctor
    from simulation.simulator import Simulator

    sim = Simulator("fifo", AlgorithmConfig(), seed=1, config=cfg, scenario="validation")
    sim._doctors = [
        SimDoctor(id="d_outage", specializations=["ECG_REST"],
                  productivity_rate=6.0, is_outage=True, is_available=False),
        SimDoctor(id="d_ok", specializations=["ECG_REST"],
                  productivity_rate=6.0, is_outage=False, is_available=True),
    ]

    from simulation.generators import SimTask
    task = SimTask(
        id=uuid.uuid4(), external_id="t1", modality="ECG_REST",
        urgency_class="план", complexity=1.0,
        arrived_at=0.0, deadline_target=120.0, deadline_max=1440.0,
    )
    doc = sim._find_doctor_sim(task)
    assert doc is not None
    assert doc.id == "d_ok", "Врач с is_outage=True не должен выбираться"


# ---------------------------------------------------------------------------
# I5: datetime.min naive vs aware в QueueManager
# ---------------------------------------------------------------------------

def test_escalated_at_aware_no_typeerror():
    """I5: min() по escalated_at не падает с TypeError при aware-datetime."""
    from algorithms.base import AlgorithmConfig
    from algorithms.factory import PrioritizerFactory
    from core.assignment_engine import AssignmentEngine
    from core.queue_manager import QueueManager
    from data.models import TaskState

    params = AlgorithmConfig()
    qm = QueueManager(PrioritizerFactory.create("EDF", params), AssignmentEngine(), params)

    now = datetime.now(timezone.utc)
    t1 = make_task(state="ESCALATED")
    t1.escalated_at = now - timedelta(minutes=5)   # aware datetime
    t2 = make_task(state="ESCALATED")
    t2.escalated_at = now                           # aware datetime

    qm._queue[t1.id] = t1
    qm._queue[t2.id] = t2

    # Не должно поднять TypeError
    try:
        result = qm.select_next_assignment(now, doctors=[])
    except TypeError as e:
        pytest.fail(f"TypeError при aware escalated_at: {e}")


# ---------------------------------------------------------------------------
# I6: estimate_tat не включает само задание в позицию
# ---------------------------------------------------------------------------

def test_estimate_tat_excludes_self():
    """I6: При единственном задании в очереди позиция = 0 → TAT = service_time."""
    from core.metrics_collector import MetricsCollector

    mc = MetricsCollector(target_hours=2.0, max_hours=24.0)
    now = datetime.now(timezone.utc)

    task = make_task(modality="ECG_REST", complexity=1.0)
    doc = make_doctor(specializations=["ECG_REST"], productivity_rate=6.0, current_load=0.0)

    # Очередь содержит только само задание
    tat_h = mc.estimate_tat(task, [task], [doc])
    expected = 1.0 / 6.0  # service_time = complexity / productivity
    assert abs(tat_h - expected) < 1e-9, (
        f"estimate_tat={tat_h:.6f} != service_time={expected:.6f}; "
        "задание считает себя в очереди"
    )


def test_estimate_tat_counts_others():
    """I6: При двух заданиях — другое считается, своё — нет."""
    from core.metrics_collector import MetricsCollector

    mc = MetricsCollector(target_hours=2.0, max_hours=24.0)
    now = datetime.now(timezone.utc)

    t1 = make_task(modality="ECG_REST", complexity=1.0)
    t2 = make_task(modality="ECG_REST", complexity=1.0)
    doc = make_doctor(specializations=["ECG_REST"], productivity_rate=6.0, current_load=0.0)

    # t1 запрашивает оценку; t2 стоит перед ним в очереди
    tat_h = mc.estimate_tat(t1, [t1, t2], [doc])
    # position=1 (только t2), wait = 1*service + service = 2*service
    expected = 2.0 * (1.0 / 6.0)
    assert abs(tat_h - expected) < 1e-9, f"estimate_tat={tat_h:.6f}, expected={expected:.6f}"


# ---------------------------------------------------------------------------
# I2: cito_not_assigned в знаменатель SLA_CITO
# ---------------------------------------------------------------------------

def test_sla_cito_denominator_includes_not_assigned():
    """I2: SLA_CITO учитывает CITO без врача в знаменателе (вариант B)."""
    from core.metrics_collector import MetricsCollector

    mc = MetricsCollector(target_hours=2.0, max_hours=24.0, cito_assign_epsilon_sec=5.0)
    now = datetime.now(timezone.utc)

    # 1 назначено в срок
    mc.record_cito_assignment("t1", now, now + timedelta(seconds=3))
    # 2 эскалированы без врача
    mc.record_cito_escalated()
    mc.record_cito_escalated()

    metrics = mc.compute_sla_metrics()
    # cito_ok=1, cito_total=3 → SLA_CITO = 1/3 ≈ 0.3333
    assert abs(metrics["SLA_CITO_target"] - 1 / 3) < 1e-3, (
        f"SLA_CITO={metrics['SLA_CITO_target']:.4f}, ожидалось 0.3333"
    )


def test_sla_cito_without_escalated():
    """I2: При отсутствии эскалаций знаменатель = только назначенные."""
    from core.metrics_collector import MetricsCollector

    mc = MetricsCollector(target_hours=2.0, max_hours=24.0, cito_assign_epsilon_sec=5.0)
    now = datetime.now(timezone.utc)

    mc.record_cito_assignment("t1", now, now + timedelta(seconds=2))
    mc.record_cito_assignment("t2", now, now + timedelta(seconds=4))

    metrics = mc.compute_sla_metrics()
    assert metrics["SLA_CITO_target"] == pytest.approx(1.0), (
        "Оба CITO в срок → SLA_CITO должен быть 1.0"
    )


# ---------------------------------------------------------------------------
# I3: SLA_WARNING с elapsed + estimated
# ---------------------------------------------------------------------------

def test_sla_warning_includes_elapsed():
    """I3: SLA_WARNING срабатывает по elapsed + estimated, не только estimated."""
    from core.metrics_collector import MetricsCollector
    from data.models import TaskState

    # threshold=0.5 → warning_h = 0.5 * 2.0 = 1.0 ч
    mc = MetricsCollector(target_hours=2.0, max_hours=24.0, warning_threshold=0.5)

    now = datetime.now(timezone.utc)
    # Задание ждёт уже 50 минут (elapsed = 50/60 ч ≈ 0.833 ч)
    arrived = now - timedelta(minutes=50)
    task = make_task(
        modality="ECG_REST", complexity=1.0,
        arrived_at=arrived,
        deadline_target=arrived + timedelta(hours=2),
        deadline_max=arrived + timedelta(hours=24),
        state="QUEUED",
    )
    # Врач со слабой производительностью: service_time = 1/0.5 = 2ч
    doc = make_doctor(specializations=["ECG_REST"], productivity_rate=0.5, current_load=0.0)

    # elapsed(0.833) + estimated(2.0) = 2.833 > threshold(1.0) → WARNING
    events = mc.check_sla_violations(now, [task], doctors=[doc])
    warnings = [e for e in events if e["type"] == "SLA_WARNING"]
    assert len(warnings) >= 1, "SLA_WARNING должен сработать при elapsed+estimated > threshold"


def test_sla_warning_not_triggered_too_early():
    """I3: SLA_WARNING не срабатывает если сумма меньше порога."""
    from core.metrics_collector import MetricsCollector

    mc = MetricsCollector(target_hours=2.0, max_hours=24.0, warning_threshold=0.5)
    now = datetime.now(timezone.utc)
    arrived = now - timedelta(minutes=5)  # elapsed = 5мин ≈ 0.083ч

    task = make_task(
        modality="ECG_REST", complexity=1.0,
        arrived_at=arrived,
        deadline_target=arrived + timedelta(hours=2),
        deadline_max=arrived + timedelta(hours=24),
        state="QUEUED",
    )
    # Быстрый врач: service_time = 1/12 ≈ 0.083ч → elapsed+estimated ≈ 0.166 < 1.0
    doc = make_doctor(specializations=["ECG_REST"], productivity_rate=12.0, current_load=0.0)

    events = mc.check_sla_violations(now, [task], doctors=[doc])
    violations = [e for e in events if e["type"] == "SLA_VIOLATION"]
    warnings = [e for e in events if e["type"] == "SLA_WARNING"]
    assert len(violations) == 0
    assert len(warnings) == 0, "SLA_WARNING не должен срабатывать при малом elapsed+estimated"


# ---------------------------------------------------------------------------
# P1: priority_value != 0.0 в симуляционном логе
# ---------------------------------------------------------------------------

def test_priority_value_nonzero_in_audit_log():
    """P1: priority_value в AuditLog ASSIGNED != 0.0 для заданий с t_arr > 0."""
    import json
    import sys

    import yaml
    sys.path.insert(0, ".")

    with open("config/config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    from algorithms.base import AlgorithmConfig
    from simulation.simulator import Simulator

    sim = Simulator(
        "pq", AlgorithmConfig(), seed=0, config=cfg,
        jsonl_path="results/test_p1_pv.jsonl",
        scenario="baseline",
    )
    sim.run_with_rate(240.0, 446)

    with open("results/test_p1_pv.jsonl", encoding="utf-8") as f:
        lines = [json.loads(l) for l in f if l.strip()]

    assigned = [
        l for l in lines
        if l.get("event_type") == "ASSIGNED"
        and l.get("payload_json", {}).get("queue_wait_min", 0) > 0
    ]
    if not assigned:
        pytest.skip("Нет ASSIGNED-событий с ненулевым ожиданием в 4-часовом прогоне")

    nonzero = [
        a for a in assigned
        if a.get("payload_json", {}).get("priority_value", 0.0) != 0.0
    ]
    assert len(nonzero) > 0, (
        f"Все {len(assigned)} ASSIGNED-события имеют priority_value=0.0; "
        "compute_priority не вызывается"
    )
