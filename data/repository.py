"""Репозитории для работы с данными через SQLAlchemy."""
import uuid
from datetime import datetime
from typing import Optional

from data.models import Assignment, AuditLogEntry, Doctor, Task, TaskState
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, task: Task) -> Task:
        self._session.add(task)
        await self._session.flush()
        return task

    async def get_by_id(self, task_id: uuid.UUID) -> Optional[Task]:
        result = await self._session.execute(
            select(Task).where(Task.id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Optional[Task]:
        result = await self._session.execute(
            select(Task).where(Task.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def get_queue(self) -> list[Task]:
        """Возвращает задания в состояниях QUEUED и ESCALATED."""
        result = await self._session.execute(
            select(Task).where(
                Task.state.in_([TaskState.QUEUED, TaskState.ESCALATED])
            ).order_by(Task.arrived_at)
        )
        return list(result.scalars().all())

    async def get_by_states(self, states: list[str]) -> list[Task]:
        result = await self._session.execute(
            select(Task).where(Task.state.in_(states))
        )
        return list(result.scalars().all())

    async def get_overdue_tasks(self, now: datetime) -> list[Task]:
        """Возвращает просроченные задания."""
        result = await self._session.execute(
            select(Task).where(
                Task.deadline_max < now,
                Task.state.in_([TaskState.QUEUED, TaskState.ASSIGNED]),
            )
        )
        return list(result.scalars().all())

    async def get_tasks_for_doctor(self, doctor_id: uuid.UUID) -> list[Task]:
        result = await self._session.execute(
            select(Task).where(
                Task.assigned_to == doctor_id,
                Task.state.in_([TaskState.ASSIGNED, TaskState.IN_PROGRESS]),
            )
        )
        return list(result.scalars().all())

    async def update_state(
        self,
        task_id: uuid.UUID,
        new_state: str,
        version: int,
        **extra_fields,
    ) -> bool:
        """Обновляет состояние с оптимистической блокировкой."""
        stmt = (
            update(Task)
            .where(Task.id == task_id, Task.version == version)
            .values(state=new_state, version=version + 1, **extra_fields)
        )
        result = await self._session.execute(stmt)
        return result.rowcount == 1

    async def list_tasks(
        self,
        state: Optional[str] = None,
        modality: Optional[str] = None,
        urgency_class: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        stmt = select(Task)
        if state:
            stmt = stmt.where(Task.state == state)
        if modality:
            stmt = stmt.where(Task.modality == modality)
        if urgency_class:
            stmt = stmt.where(Task.urgency_class == urgency_class)
        stmt = stmt.order_by(Task.arrived_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class DoctorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, doctor: Doctor) -> Doctor:
        self._session.add(doctor)
        await self._session.flush()
        return doctor

    async def get_by_id(self, doctor_id: uuid.UUID) -> Optional[Doctor]:
        result = await self._session.execute(
            select(Doctor).where(Doctor.id == doctor_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_hash(self, hash_val: str) -> Optional[Doctor]:
        result = await self._session.execute(
            select(Doctor).where(Doctor.external_doctor_id_hash == hash_val)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[Doctor]:
        result = await self._session.execute(select(Doctor))
        return list(result.scalars().all())

    async def get_available(self) -> list[Doctor]:
        """Возвращает доступных врачей."""
        result = await self._session.execute(
            select(Doctor).where(Doctor.is_available.is_(True))
        )
        return list(result.scalars().all())

    async def update_load(
        self, doctor_id: uuid.UUID, delta: float
    ) -> None:
        """Изменяет текущую нагрузку врача."""
        stmt = (
            update(Doctor)
            .where(Doctor.id == doctor_id)
            .values(current_load=Doctor.current_load + delta)
        )
        await self._session.execute(stmt)

    async def set_availability(
        self, doctor_id: uuid.UUID, is_available: bool
    ) -> None:
        stmt = (
            update(Doctor)
            .where(Doctor.id == doctor_id)
            .values(is_available=is_available)
        )
        await self._session.execute(stmt)

    async def upsert_from_config(self, doctor_data: dict) -> Doctor:
        """Создаёт врача из конфигурации, если его ещё нет."""
        import hashlib

        doctor_id_str = doctor_data["id"]
        hash_val = hashlib.sha256(doctor_id_str.encode()).hexdigest()
        existing = await self.get_by_external_hash(hash_val)
        if existing:
            return existing
        doctor = Doctor(
            external_doctor_id_hash=hash_val,
            specializations=doctor_data["specializations"],
            productivity_rate=doctor_data.get("productivity_rate", 1.0),
            is_available=True,
            current_load=0.0,
        )
        return await self.create(doctor)


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(self, entry: AuditLogEntry) -> AuditLogEntry:
        """Добавляет запись журнала."""
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def get_events_by_task(self, task_id: uuid.UUID) -> list[AuditLogEntry]:
        result = await self._session.execute(
            select(AuditLogEntry)
            .where(AuditLogEntry.task_id == task_id)
            .order_by(AuditLogEntry.timestamp)
        )
        return list(result.scalars().all())

    async def get_events_by_period(
        self, start: datetime, end: datetime
    ) -> list[AuditLogEntry]:
        result = await self._session.execute(
            select(AuditLogEntry)
            .where(
                AuditLogEntry.timestamp >= start,
                AuditLogEntry.timestamp <= end,
            )
            .order_by(AuditLogEntry.timestamp)
        )
        return list(result.scalars().all())

    async def get_events_by_type(self, event_type: str) -> list[AuditLogEntry]:
        result = await self._session.execute(
            select(AuditLogEntry)
            .where(AuditLogEntry.event_type == event_type)
            .order_by(AuditLogEntry.timestamp)
        )
        return list(result.scalars().all())
