"""Тесты QueueManager."""
from datetime import datetime, timedelta, timezone

import pytest
from algorithms.base import AlgorithmConfig
from algorithms.factory import PrioritizerFactory
from core.assignment_engine import AssignmentEngine
from core.queue_manager import QueueManager
from data.models import TaskState
from tests.conftest import make_doctor, make_task


def make_qm(algo="EDF"):
    params = AlgorithmConfig(
        type=algo,
        priority_weights={"CITO": 1000, "план": 1},
        beta=0.05,
        delta=1e-6,
        epsilon=1.0,
    )
    prioritizer = PrioritizerFactory.create(algo, params)
    ae = AssignmentEngine()
    return QueueManager(prioritizer, ae, params)


def test_escalated_processed_before_queued():
    """ESCALATED-задания обрабатываются до QUEUED."""
    now = datetime.now(timezone.utc)
    qm = make_qm()
    plan_task = make_task(urgency_class="план", modality="ECG_REST")
    esc_task  = make_task(urgency_class="план", modality="ECG_REST", state="ESCALATED")
    esc_task.escalated_at = now - timedelta(minutes=5)
    qm._queue[plan_task.id] = plan_task
    qm._queue[esc_task.id]  = esc_task
    doc = make_doctor(specializations=["ECG_REST"])
    result = qm.select_next_assignment(now, [doc])
    assert result is not None
    assert result[0].id == esc_task.id


def test_escalated_fifo_by_escalated_at():
    """Два ESCALATED — обрабатываются по escalated_at (FIFO)."""
    now = datetime.now(timezone.utc)
    qm = make_qm()
    e1 = make_task(state="ESCALATED", modality="ECG_REST")
    e1.escalated_at = now - timedelta(minutes=10)
    e2 = make_task(state="ESCALATED", modality="ECG_REST")
    e2.escalated_at = now - timedelta(minutes=5)
    qm._queue[e1.id] = e1
    qm._queue[e2.id] = e2
    doc = make_doctor(specializations=["ECG_REST"])
    result = qm.select_next_assignment(now, [doc])
    assert result[0].id == e1.id


def test_no_doctor_returns_none():
    """Нет совместимого врача → None."""
    qm = make_qm()
    task = make_task(modality="EEG")
    qm.enqueue(task)
    doc = make_doctor(specializations=["ECG_REST"])  # несовместимый
    result = qm.select_next_assignment(datetime.now(timezone.utc), [doc])
    assert result is None


def test_hot_swap_algorithm():
    """Горячая замена: следующий sort() использует новый алгоритм."""
    qm = make_qm("EDF")
    assert qm.get_current_algorithm() == "EDF"
    qm.set_algorithm("FIFO")
    assert qm.get_current_algorithm() == "FIFO"
    # Следующее назначение использует FIFO-алгоритм
    now = datetime.now(timezone.utc)
    task = make_task(modality="ECG_REST")
    qm.enqueue(task)
    doc = make_doctor(specializations=["ECG_REST"])
    result = qm.select_next_assignment(now, [doc])
    assert result is not None


def test_dispatch_cito_check_after_batch():
    """dispatch_cito_check переводит CITO без врача в ESCALATED."""
    qm = make_qm()
    now = datetime.now(timezone.utc)
    cito = make_task(urgency_class="CITO", modality="EEG")  # несовместимая специализация
    qm._queue[cito.id] = cito
    # Нет врача с EEG
    docs = [make_doctor(specializations=["ECG_REST"])]
    escalated = qm.dispatch_cito_check(now, docs)
    assert len(escalated) == 1
    assert escalated[0].state == TaskState.ESCALATED
    assert escalated[0].escalated_at == now


def test_enqueue_sets_queued():
    """enqueue() устанавливает state=QUEUED."""
    qm = make_qm()
    task = make_task()
    qm.enqueue(task)
    assert task.state == TaskState.QUEUED
    assert task.id in qm._queue


def test_get_queue_state_only_active():
    """get_queue_state() возвращает только QUEUED и ESCALATED."""
    qm = make_qm()
    q_task = make_task(state="QUEUED")
    e_task = make_task(state="ESCALATED")
    done   = make_task(state="DONE")
    qm._queue[q_task.id] = q_task
    qm._queue[e_task.id] = e_task
    qm._queue[done.id]   = done
    state = qm.get_queue_state()
    ids = {t.id for t in state}
    assert q_task.id in ids
    assert e_task.id in ids
    assert done.id not in ids
