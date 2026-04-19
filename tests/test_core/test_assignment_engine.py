"""Тесты AssignmentEngine."""
from datetime import datetime, timezone

import pytest
from core.assignment_engine import AssignmentEngine
from tests.conftest import make_doctor, make_task


@pytest.fixture
def engine():
    return AssignmentEngine()


def test_wll_selects_min_normalized_load(engine):
    """WLL выбирает врача с минимальной L_q/μ_q."""
    task = make_task(modality="ECG_REST")
    d1 = make_doctor(specializations=["ECG_REST"], productivity_rate=1.0, current_load=2.0)
    d2 = make_doctor(specializations=["ECG_REST"], productivity_rate=1.0, current_load=1.0)
    d3 = make_doctor(specializations=["ECG_REST"], productivity_rate=2.0, current_load=2.0)
    # d1: 2/1=2; d2: 1/1=1; d3: 2/2=1 → d2 и d3 равны → выберет первый из них
    doc = engine.find_doctor(task, [d1, d2, d3])
    # Главное — d1 (нагрузка 2) не выбран
    assert doc.id != d1.id


def test_wll_specialization_filter(engine):
    """Врач без нужной специализации не попадает в eligible."""
    task = make_task(modality="ECG_REST")
    d_wrong = make_doctor(specializations=["HOLTER"])
    d_right = make_doctor(specializations=["ECG_REST"])
    doc = engine.find_doctor(task, [d_wrong, d_right])
    assert doc.id == d_right.id


def test_wll_unavailable_doctor_excluded(engine):
    """Недоступный врач не попадает в eligible."""
    task = make_task(modality="ECG_REST")
    d_busy = make_doctor(specializations=["ECG_REST"], is_available=False)
    d_free = make_doctor(specializations=["ECG_REST"], is_available=True)
    doc = engine.find_doctor(task, [d_busy, d_free])
    assert doc.id == d_free.id


def test_wll_no_compatible_returns_none(engine):
    """Нет совместимых врачей → None."""
    task = make_task(modality="EEG")
    d1 = make_doctor(specializations=["ECG_REST"])
    doc = engine.find_doctor(task, [d1])
    assert doc is None


def test_assign_increases_load(engine):
    """assign() увеличивает doctor.current_load на task.complexity."""
    task = make_task(complexity=3.0, modality="ECG_REST")
    doc  = make_doctor(specializations=["ECG_REST"], current_load=1.0)
    engine.assign(task, doc, algorithm_used="EDF", now=datetime.now(timezone.utc))
    assert doc.current_load == pytest.approx(4.0)


def test_complete_decreases_load(engine):
    """complete() уменьшает doctor.current_load на task.complexity."""
    from data.models import TaskState
    task = make_task(complexity=3.0, modality="ECG_REST")
    doc  = make_doctor(specializations=["ECG_REST"], current_load=5.0)
    now = datetime.now(timezone.utc)
    task.started_at = now
    task.arrived_at = now
    task.state = TaskState.IN_PROGRESS
    engine.complete(task, doc, now=now)
    assert doc.current_load == pytest.approx(2.0)
    assert doc.is_available is True


def test_assign_sets_state(engine):
    """assign() устанавливает task.state = ASSIGNED."""
    from data.models import TaskState
    task = make_task(modality="ECG_REST")
    doc = make_doctor(specializations=["ECG_REST"])
    engine.assign(task, doc, algorithm_used="FIFO", now=datetime.now(timezone.utc))
    assert task.state == TaskState.ASSIGNED


def test_wll_tie_break_is_deterministic_by_id(engine):
    """При равной нормированной нагрузке выбирается врач с минимальным id."""
    task = make_task(modality="ECG_REST")
    # Одинаковый score: 2/2 = 1 и 1/1 = 1
    d2 = make_doctor(specializations=["ECG_REST"], productivity_rate=2.0, current_load=2.0)
    d1 = make_doctor(specializations=["ECG_REST"], productivity_rate=1.0, current_load=1.0)

    # Нам важно, что правило tie-break не зависит от порядка списка.
    chosen_a = engine.find_doctor(task, [d2, d1])
    chosen_b = engine.find_doctor(task, [d1, d2])
    expected_id = min(str(d1.id), str(d2.id))
    assert str(chosen_a.id) == expected_id
    assert str(chosen_b.id) == expected_id
