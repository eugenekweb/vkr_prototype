"""Логика выбора врача и фиксации жизненного цикла назначения."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from data.models import Assignment, Doctor, Task, TaskState

logger = logging.getLogger(__name__)


class AssignmentEngine:
    """Компонент назначения и завершения задач."""

    def find_doctor(self, task: Task, doctors: list[Doctor]) -> Optional[Doctor]:
        """Выбирает доступного совместимого врача с минимальной нормированной нагрузкой."""
        eligible = [
            d for d in doctors
            if d.is_available and task.modality in d.specializations
        ]
        if not eligible:
            return None
        # При равенстве используем детерминированный tie-break по id.
        return min(eligible, key=lambda d: (d.current_load / d.productivity_rate, str(d.id)))

    def assign(
        self,
        task: Task,
        doctor: Doctor,
        algorithm_used: str,
        now: Optional[datetime] = None,
    ) -> Assignment:
        """Фиксирует назначение и возвращает запись Assignment."""
        if now is None:
            now = datetime.now(timezone.utc)
        task.state = TaskState.ASSIGNED
        task.assigned_to = doctor.id
        task.version += 1
        doctor.current_load += task.complexity
        doctor.is_available = False
        assignment = Assignment(
            id=uuid.uuid4(),
            task_id=task.id,
            doctor_id=doctor.id,
            assigned_at=now,
            algorithm_used=algorithm_used,
        )
        logger.debug(
            "Assigned task %s → doctor %s (algo=%s, load_after=%.2f)",
            task.id, doctor.id, algorithm_used, doctor.current_load,
        )
        return assignment

    def start(self, task: Task, now: Optional[datetime] = None) -> None:
        """Переводит задачу из ASSIGNED в IN_PROGRESS."""
        if now is None:
            now = datetime.now(timezone.utc)
        task.state = TaskState.IN_PROGRESS
        task.started_at = now
        task.version += 1

    def complete(
        self,
        task: Task,
        doctor: Doctor,
        now: Optional[datetime] = None,
    ) -> dict:
        """Переводит задачу в DONE и возвращает вычисленные метрики."""
        if now is None:
            now = datetime.now(timezone.utc)
        task.state = TaskState.DONE
        task.done_at = now
        task.version += 1
        doctor.current_load = max(0.0, doctor.current_load - task.complexity)
        doctor.is_available = True
        tat_min = (now - task.arrived_at).total_seconds() / 60.0
        delta_target_min = (task.deadline_target - task.arrived_at).total_seconds() / 60.0
        delta_max_min = (task.deadline_max - task.arrived_at).total_seconds() / 60.0
        return {
            "TAT": round(tat_min, 2),
            "sla_target_met": tat_min <= delta_target_min,
            "sla_max_met": tat_min <= delta_max_min,
            "complexity": task.complexity,
            "duration_h": (now - task.started_at).total_seconds() / 3600.0
            if task.started_at else None,
        }
