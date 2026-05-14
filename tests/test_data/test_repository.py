"""Тесты для data.repository с мокнутой AsyncSession."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from data.models import AuditLogEntry, Doctor, Task, TaskState
from data.repository import AuditRepository, DoctorRepository, TaskRepository


class FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)


class FakeResult:
    def __init__(self, items=None, scalar=None, rowcount=1):
        self._items = items or []
        self._scalar = scalar
        self.rowcount = rowcount

    def scalars(self):
        return FakeScalarResult(self._items)

    def scalar_one_or_none(self):
        return self._scalar


@pytest.fixture
def session():
    session = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def task_repo(session):
    return TaskRepository(session)


@pytest.fixture
def doctor_repo(session):
    return DoctorRepository(session)


@pytest.fixture
def audit_repo(session):
    return AuditRepository(session)


@pytest.fixture
def task():
    now = datetime.now(timezone.utc)
    obj = Task()
    obj.id = uuid.uuid4()
    obj.external_id = f"task-{obj.id}"
    obj.modality = "ECG_REST"
    obj.urgency_class = "план"
    obj.complexity = 1.0
    obj.arrived_at = now
    obj.deadline_target = now + timedelta(hours=2)
    obj.deadline_max = now + timedelta(hours=24)
    obj.state = TaskState.QUEUED.value
    obj.assigned_to = None
    obj.started_at = None
    obj.done_at = None
    obj.escalated_at = None
    obj.version = 0
    return obj


@pytest.fixture
def doctor():
    obj = Doctor()
    obj.id = uuid.uuid4()
    obj.external_doctor_id_hash = "hash-1"
    obj.specializations = ["ECG_REST"]
    obj.productivity_rate = 1.0
    obj.is_available = True
    obj.current_load = 0.0
    return obj


@pytest.fixture
def audit_entry(task):
    entry = AuditLogEntry()
    entry.id = uuid.uuid4()
    entry.event_type = "RECEIVED"
    entry.task_id = task.id
    entry.actor = "system"
    entry.timestamp = datetime.now(timezone.utc)
    entry.algorithm_used = "EDF"
    entry.queue_depth = 1
    entry.payload_json = {"modality": "ECG_REST"}
    return entry


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_task_repository_create_and_get_by_id(task_repo, session, task):
    session.execute = AsyncMock(return_value=FakeResult(scalar=task))

    created = await task_repo.create(task)
    assert created is task
    session.add.assert_called_once_with(task)
    session.flush.assert_awaited_once()

    found = await task_repo.get_by_id(task.id)
    assert found is task


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_task_repository_get_by_external_id(task_repo, session, task):
    session.execute = AsyncMock(return_value=FakeResult(scalar=task))

    found = await task_repo.get_by_external_id(task.external_id)
    assert found is task


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_task_repository_get_queue(task_repo, session, task):
    queued = task
    escalated = Task()
    escalated.id = uuid.uuid4()
    escalated.external_id = f"task-{escalated.id}"
    escalated.state = TaskState.ESCALATED.value
    session.execute = AsyncMock(return_value=FakeResult(items=[queued, escalated]))

    result = await task_repo.get_queue()
    assert result == [queued, escalated]


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_task_repository_get_by_states(task_repo, session, task):
    session.execute = AsyncMock(return_value=FakeResult(items=[task]))

    result = await task_repo.get_by_states([TaskState.QUEUED.value])
    assert result == [task]


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_task_repository_get_overdue_tasks(task_repo, session, task):
    session.execute = AsyncMock(return_value=FakeResult(items=[task]))

    result = await task_repo.get_overdue_tasks(datetime.now(timezone.utc))
    assert result == [task]


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_task_repository_get_tasks_for_doctor(task_repo, session, task):
    doctor_id = uuid.uuid4()
    task.assigned_to = doctor_id
    task.state = TaskState.ASSIGNED.value
    session.execute = AsyncMock(return_value=FakeResult(items=[task]))

    result = await task_repo.get_tasks_for_doctor(doctor_id)
    assert result == [task]


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_task_repository_update_state_success(task_repo, session):
    session.execute = AsyncMock(return_value=FakeResult(rowcount=1))

    updated = await task_repo.update_state(
        task_id=uuid.uuid4(),
        new_state=TaskState.DONE.value,
        version=3,
        done_at=datetime.now(timezone.utc),
    )
    assert updated is True


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_task_repository_update_state_conflict(task_repo, session):
    session.execute = AsyncMock(return_value=FakeResult(rowcount=0))

    updated = await task_repo.update_state(
        task_id=uuid.uuid4(),
        new_state=TaskState.DONE.value,
        version=3,
    )
    assert updated is False


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_task_repository_list_tasks_filters(task_repo, session, task):
    session.execute = AsyncMock(return_value=FakeResult(items=[task]))

    result = await task_repo.list_tasks(
        state=TaskState.QUEUED.value,
        modality=task.modality,
        urgency_class=task.urgency_class,
        limit=10,
        offset=0,
    )
    assert result == [task]


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_doctor_repository_create_and_get_by_id(doctor_repo, session, doctor):
    session.execute = AsyncMock(return_value=FakeResult(scalar=doctor))

    created = await doctor_repo.create(doctor)
    assert created is doctor
    session.add.assert_called_once_with(doctor)
    session.flush.assert_awaited_once()

    found = await doctor_repo.get_by_id(doctor.id)
    assert found is doctor


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_doctor_repository_get_by_external_hash(doctor_repo, session, doctor):
    session.execute = AsyncMock(return_value=FakeResult(scalar=doctor))

    found = await doctor_repo.get_by_external_hash(doctor.external_doctor_id_hash)
    assert found is doctor


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_doctor_repository_get_all_and_available(doctor_repo, session, doctor):
    session.execute = AsyncMock(return_value=FakeResult(items=[doctor]))
    all_docs = await doctor_repo.get_all()
    assert all_docs == [doctor]

    session.execute = AsyncMock(return_value=FakeResult(items=[doctor]))
    available = await doctor_repo.get_available()
    assert available == [doctor]


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_doctor_repository_update_load_and_availability(doctor_repo, session):
    session.execute = AsyncMock(return_value=FakeResult(rowcount=1))

    await doctor_repo.update_load(uuid.uuid4(), 0.5)
    await doctor_repo.set_availability(uuid.uuid4(), False)

    assert session.execute.await_count == 2


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_doctor_repository_upsert_from_config_existing(doctor_repo, session, doctor):
    session.execute = AsyncMock(return_value=FakeResult(scalar=doctor))
    doctor_repo.get_by_external_hash = AsyncMock(return_value=doctor)

    result = await doctor_repo.upsert_from_config({"id": "abc", "specializations": ["ECG_REST"]})
    assert result is doctor
    doctor_repo.get_by_external_hash.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_doctor_repository_upsert_from_config_new(doctor_repo, session):
    created = Doctor()
    created.id = uuid.uuid4()
    created.external_doctor_id_hash = "new-hash"
    created.specializations = ["EEG"]
    created.productivity_rate = 1.2
    created.is_available = True
    created.current_load = 0.0

    doctor_repo.get_by_external_hash = AsyncMock(return_value=None)
    doctor_repo.create = AsyncMock(return_value=created)

    result = await doctor_repo.upsert_from_config(
        {"id": "new-doctor", "specializations": ["EEG"], "productivity_rate": 1.2}
    )
    assert result is created
    doctor_repo.create.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.data
@pytest.mark.asyncio
async def test_audit_repository_log_and_getters(audit_repo, session, audit_entry):
    session.execute = AsyncMock(return_value=FakeResult(items=[audit_entry]))

    logged = await audit_repo.log(audit_entry)
    assert logged is audit_entry
    session.add.assert_called_once_with(audit_entry)
    session.flush.assert_awaited_once()

    by_task = await audit_repo.get_events_by_task(audit_entry.task_id)
    assert by_task == [audit_entry]

    by_period = await audit_repo.get_events_by_period(
        audit_entry.timestamp - timedelta(minutes=1),
        audit_entry.timestamp + timedelta(minutes=1),
    )
    assert by_period == [audit_entry]

    by_type = await audit_repo.get_events_by_type(audit_entry.event_type)
    assert by_type == [audit_entry]
