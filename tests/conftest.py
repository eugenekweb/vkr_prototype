"""
Общие фикстуры для всех тестов.
Используем SQLite in-memory для тестов без PostgreSQL.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from algorithms.base import AlgorithmConfig


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def default_params() -> AlgorithmConfig:
    return AlgorithmConfig(
        type="EDF",
        beta=0.05,
        delta=1e-6,
        epsilon=1.0,
        priority_weights={"CITO": 1000, "план": 1},
    )


def make_task(
    urgency_class: str = "план",
    modality: str = "ECG_REST",
    complexity: float = 1.0,
    arrived_at: datetime = None,
    deadline_target: datetime = None,
    deadline_max: datetime = None,
    state: str = "QUEUED",
):
    """Фабрика тестовых заданий."""
    from data.models import Task
    now = arrived_at or datetime.now(timezone.utc)
    task = Task()
    task.id = uuid.uuid4()
    task.external_id = f"test-{task.id}"
    task.modality = modality
    task.urgency_class = urgency_class
    task.complexity = complexity
    task.arrived_at = now
    task.deadline_target = deadline_target or (now + timedelta(hours=2))
    task.deadline_max = deadline_max or (now + timedelta(hours=24))
    task.state = state
    task.version = 0
    task.assigned_to = None
    task.started_at = None
    task.done_at = None
    task.escalated_at = None
    return task


def make_doctor(
    specializations: list = None,
    productivity_rate: float = 1.0,
    is_available: bool = True,
    current_load: float = 0.0,
):
    """Фабрика тестовых врачей."""
    from data.models import Doctor
    doctor = Doctor()
    doctor.id = uuid.uuid4()
    doctor.external_doctor_id_hash = "test-hash"
    doctor.specializations = specializations or ["ECG_REST"]
    doctor.productivity_rate = productivity_rate
    doctor.is_available = is_available
    doctor.current_load = current_load
    return doctor
