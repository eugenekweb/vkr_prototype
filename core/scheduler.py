"""Фоновый цикл диспетчеризации для операционного контура."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from core.audit_logger import AuditLogger
from core.metrics_collector import MetricsCollector
from core.queue_manager import QueueManager
from data.models import EventType, Task, UrgencyClass

logger = logging.getLogger(__name__)

_DISPATCH_INTERVAL_SEC = 1.0


class Scheduler:
    """Фоновый планировщик операционного контура."""

    def __init__(
        self,
        queue_manager: QueueManager,
        assignment_engine=None,
        metrics_collector: MetricsCollector = None,
        audit_logger: AuditLogger = None,
        session_factory=None,
        dispatch_interval: float = _DISPATCH_INTERVAL_SEC,
    ) -> None:
        self._qm = queue_manager
        self._mc = metrics_collector
        self._al = audit_logger
        self._session_factory = session_factory
        self._dispatch_interval = dispatch_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Scheduler started (interval=%.1fs)", self._dispatch_interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.dispatch_cycle()
            except Exception as exc:
                logger.error("Dispatch cycle error: %s", exc, exc_info=True)
            await asyncio.sleep(self._dispatch_interval)

    async def dispatch_cycle(self) -> None:
        """Выполняет один цикл диспетчеризации."""
        now = datetime.now(timezone.utc)
        doctors = await self._get_doctors()
        queue_state = self._qm.get_queue_state()
        sla_monitor_state = self._qm.get_sla_monitor_state()

        sla_events = self._mc.check_sla_violations(now, sla_monitor_state, doctors)
        for ev in sla_events:
            task_id = ev.get("task_id")
            await self._al.log_event(
                event_type=ev["type"],
                task_id=task_id,
                queue_depth=len(queue_state),
                payload=ev,
            )
            if ev["type"] == "SLA_VIOLATION" and task_id:
                escalated = self._qm.escalate(task_id, now)
                if escalated and self._session_factory:
                    await self._persist_escalation(escalated, now)

        assignments_made = 0
        while True:
            result = self._qm.select_next_assignment(now, doctors)
            if result is None:
                break
            task, doctor, priority_value, queue_size_at_assignment = result
            assignment = self._qm.assign(task, doctor, now)
            assignments_made += 1

            if self._session_factory:
                await self._persist_assignment(task, doctor, assignment)

            await self._al.log_event(
                event_type=EventType.ASSIGNED,
                task_id=task.id,
                actor=str(doctor.id),
                algorithm_used=assignment.algorithm_used,
                queue_depth=len(self._qm.get_queue_state()),
                payload={
                    "doctor_id": str(doctor.id),
                    "assigned_at": assignment.assigned_at.isoformat(),
                    "queue_wait_time_min": (
                        (assignment.assigned_at - task.arrived_at).total_seconds() / 60
                    ),
                    "complexity": task.complexity,
                    "priority_value": round(priority_value, 6),
                    "queue_size_at_assignment": queue_size_at_assignment,
                },
            )

            if task.urgency_class == UrgencyClass.CITO:
                self._mc.record_cito_assignment(task.id, task.arrived_at, now)

        escalated_tasks = self._qm.dispatch_cito_check(now, doctors)
        for task in escalated_tasks:
            await self._al.log_event(
                event_type=EventType.CITO_ESCALATED,
                task_id=task.id,
                queue_depth=len(self._qm.get_queue_state()),
                payload={"triggered_at": now.isoformat(), "assigned_to": None},
            )
            self._mc.record_cito_escalated()
            if self._session_factory:
                await self._persist_escalation(task, now)

        if assignments_made > 0:
            logger.debug("Dispatch cycle: %d assignments", assignments_made)

    async def _get_doctors(self):
        """Возвращает список врачей."""
        if self._session_factory:
            from data.repository import DoctorRepository
            async with self._session_factory() as session:
                async with session.begin():
                    repo = DoctorRepository(session)
                    return await repo.get_all()
        return []

    async def _persist_assignment(self, task, doctor, assignment):
        """Сохраняет изменения состояния задания и врача."""
        from data.repository import DoctorRepository, TaskRepository
        async with self._session_factory() as session:
            async with session.begin():
                task_repo = TaskRepository(session)
                doc_repo = DoctorRepository(session)
                db_task = await task_repo.get_by_id(task.id)
                if db_task:
                    db_task.state = task.state
                    db_task.assigned_to = task.assigned_to
                    db_task.version = task.version
                db_doctor = await doc_repo.get_by_id(doctor.id)
                if db_doctor:
                    db_doctor.current_load = doctor.current_load
                    db_doctor.is_available = doctor.is_available
                session.add(assignment)

    async def _persist_escalation(self, task, now: datetime) -> None:
        """Сохраняет эскалацию в БД."""
        from data.repository import TaskRepository
        async with self._session_factory() as session:
            async with session.begin():
                repo = TaskRepository(session)
                await repo.update_state(
                    task.id,
                    new_state="ESCALATED",
                    version=task.version - 1,
                    escalated_at=now,
                )
