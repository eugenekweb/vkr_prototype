"""Управление in-memory очередью и выбором следующего назначения."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from algorithms.base import AlgorithmConfig, IPrioritizer
from algorithms.factory import PrioritizerFactory
from core.assignment_engine import AssignmentEngine
from data.models import Assignment, Doctor, Task, TaskState, UrgencyClass

logger = logging.getLogger(__name__)


class QueueManager:
    """Хранит очередь в памяти и делегирует выбор врача AssignmentEngine."""

    def __init__(
        self,
        prioritizer: IPrioritizer,
        assignment_engine: AssignmentEngine,
        params: AlgorithmConfig,
    ) -> None:
        self._prioritizer = prioritizer
        self._assignment_engine = assignment_engine
        self._params = params
        self._queue: dict[uuid.UUID, Task] = {}

    def enqueue(self, task: Task, force_queued: bool = True) -> None:
        """Добавляет задание в очередь."""
        if force_queued:
            task.state = TaskState.QUEUED
        self._queue[task.id] = task
        logger.debug("Enqueued task %s (modality=%s, urgency=%s)", task.id, task.modality, task.urgency_class)

    def remove(self, task_id: uuid.UUID) -> None:
        self._queue.pop(task_id, None)

    def get_queue_state(self) -> list[Task]:
        """Возвращает задания в состояниях QUEUED и ESCALATED."""
        return [
            t for t in self._queue.values()
            if t.state in (TaskState.QUEUED, TaskState.ESCALATED)
        ]

    def get_sla_monitor_state(self) -> list[Task]:
        """Возвращает задания, которые участвуют в SLA-мониторинге."""
        return [
            t for t in self._queue.values()
            if t.state in (TaskState.QUEUED, TaskState.ESCALATED, TaskState.ASSIGNED)
        ]

    def get_all_in_memory(self) -> list[Task]:
        return list(self._queue.values())

    def select_next_assignment(
        self, t: datetime, doctors: list[Doctor]
    ) -> Optional[tuple[Task, Doctor, float, int]]:
        """Выбирает пару (task, doctor) для одного назначения."""
        queue = self.get_queue_state()
        if not queue:
            return None
        queue_size = len(queue)

        escalated = [j for j in queue if j.state == TaskState.ESCALATED]
        if escalated:
            _MIN_DT_AWARE = datetime.min.replace(tzinfo=timezone.utc)
            j_star = min(escalated, key=lambda j: j.escalated_at or _MIN_DT_AWARE)
            priority_value = 0.0
        else:
            queued = [j for j in queue if j.state == TaskState.QUEUED]
            if not queued:
                return None
            sorted_queue = self._prioritizer.sort(queued, t, self._params)
            if not sorted_queue:
                return None
            j_star = sorted_queue[0]
            try:
                priority_value = self._prioritizer.compute_priority(j_star, t, self._params)
            except Exception:
                priority_value = 0.0

        q_star = self._assignment_engine.find_doctor(j_star, doctors)
        if q_star is None:
            return None

        return (j_star, q_star, priority_value, queue_size)

    def assign(
        self,
        task: Task,
        doctor: Doctor,
        now: datetime,
    ) -> Assignment:
        """
        Фиксирует назначение через AssignmentEngine.
        После вызова задание покидает Q(t).
        """
        assignment = self._assignment_engine.assign(
            task, doctor, self._params.type, now
        )
        self.remove(task.id)
        return assignment

    def set_algorithm(self, algorithm_type: str, params: Optional[AlgorithmConfig] = None) -> None:
        """
        Атомарная замена IPrioritizer без остановки системы.
        Следующий вызов sort() использует новый алгоритм.
        """
        self._prioritizer = PrioritizerFactory.create(algorithm_type)
        if params:
            self._params = params
        else:
            self._params.type = algorithm_type
        logger.info("Algorithm changed to %s", algorithm_type)

    def get_current_algorithm(self) -> str:
        return self._params.type

    def escalate(self, task_id: uuid.UUID, now: datetime) -> Optional[Task]:
        """Принудительная эскалация задания → ESCALATED."""
        task = self._queue.get(task_id)
        if task is None:
            return None
        task.state = TaskState.ESCALATED
        task.escalated_at = now
        task.version += 1
        logger.info("Task %s escalated at %s", task_id, now)
        return task

    def dispatch_cito_check(self, t: datetime, doctors: list[Doctor]) -> list[Task]:
        """Эскалирует CITO-задачи без доступного совместимого врача."""
        escalated: list[Task] = []
        cito_queued = [
            j for j in self._queue.values()
            if j.state == TaskState.QUEUED and j.urgency_class == UrgencyClass.CITO
        ]
        for task in cito_queued:
            compatible_doctor = self._assignment_engine.find_doctor(task, doctors)
            if compatible_doctor is None:
                task.state = TaskState.ESCALATED
                task.escalated_at = t
                task.version += 1
                escalated.append(task)
                logger.info("CITO task %s escalated (no available doctor)", task.id)
        return escalated
