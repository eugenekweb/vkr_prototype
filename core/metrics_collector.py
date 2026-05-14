"""Сбор метрик и контроль SLA."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Optional

from data.models import Doctor, Task, TaskState, UrgencyClass

logger = logging.getLogger(__name__)

_SECONDS_PER_HOUR = 3600.0


class MetricsSnapshot:
    """Снимок метрик."""
    __slots__ = [
        "sla_cito_target", "sla_plan_target", "sla_plan_max",
        "load_variance", "online_load_variance", "sigma_w2_final",
        "queue_depth", "queue_by_modality",
        "doctors_load", "timestamp",
    ]

    def __init__(self) -> None:
        self.sla_cito_target: float = 1.0
        self.sla_plan_target: float = 1.0
        self.sla_plan_max: float = 1.0
        self.online_load_variance: float = 0.0
        self.sigma_w2_final: float = 0.0
        self.load_variance: float = 0.0
        self.queue_depth: int = 0
        self.queue_by_modality: dict[str, int] = {}
        self.doctors_load: list[dict] = []
        self.timestamp: datetime = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "SLA_CITO_target": self.sla_cito_target,
            "SLA_plan_target": self.sla_plan_target,
            "SLA_plan_max": self.sla_plan_max,
            "online_load_variance": self.online_load_variance,
            "sigma_w2_final": self.sigma_w2_final,
            # устаревший алиас для совместимости
            "load_variance": self.load_variance,
            "queue_depth": self.queue_depth,
            "queue_by_modality": self.queue_by_modality,
            "doctors_load": self.doctors_load,
            "timestamp": self.timestamp.isoformat(),
        }


class MetricsCollector:
    """Собирает SLA-метрики и оценки очереди."""

    def __init__(
        self,
        target_hours: float = 2.0,
        max_hours: float = 24.0,
        warning_threshold: float = 0.5,
        cito_assign_epsilon_sec: float = 5.0,
    ) -> None:
        self._target_hours = target_hours
        self._max_hours = max_hours
        self._warning_threshold = warning_threshold
        self._cito_epsilon_h = cito_assign_epsilon_sec / _SECONDS_PER_HOUR

        self._completed_tasks: list[Task] = []
        self._cito_assignments: dict = {}
        self._cito_not_assigned: int = 0
        self._queue_timeline: list[tuple[float, int]] = []

        self._handlers: dict[str, list[Callable]] = defaultdict(list)


    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event_type: str, **kwargs) -> None:
        for handler in self._handlers.get(event_type, []):
            try:
                handler(event_type=event_type, **kwargs)
            except Exception as exc:
                logger.error("MetricsCollector handler error: %s", exc)

    def record_completed(self, task: Task) -> None:
        """Регистрирует завершённое задание."""
        self._completed_tasks.append(task)

    def record_cito_assignment(
        self, task_id, t_arr: datetime, t_assign: datetime
    ) -> None:
        """Регистрирует момент назначения CITO-задания."""
        self._cito_assignments[task_id] = (t_arr, t_assign)

    def record_cito_escalated(self) -> None:
        """Регистрирует CITO-задание, не получившее врача сразу."""
        self._cito_not_assigned += 1

    def record_queue_length(self, timestamp_min: float, queue_length: int) -> None:
        """Регистрирует длину очереди в момент изменения ее состава."""
        timestamp_min = max(0.0, float(timestamp_min))
        queue_length = max(0, int(queue_length))
        if self._queue_timeline and self._queue_timeline[-1][0] == timestamp_min:
            self._queue_timeline[-1] = (timestamp_min, queue_length)
        else:
            self._queue_timeline.append((timestamp_min, queue_length))

    @staticmethod
    def _weighted_queue_metrics(
        timeline: list[tuple[float, int]],
        start_min: float,
        end_min: float,
    ) -> tuple[float, int, float]:
        """Считает time-average, максимум и time-weighted p95 по профилю очереди."""
        if end_min <= start_min:
            return 0.0, 0, 0.0

        points = sorted((float(t), int(q)) for t, q in timeline)
        if not points:
            return 0.0, 0, 0.0

        q_at_start = 0
        for t, q in points:
            if t <= start_min:
                q_at_start = q
            else:
                break

        if points[0][0] > start_min:
            points = [(start_min, q_at_start), *points]
        elif points[0][0] < start_min:
            points = [(start_min, q_at_start), *[(t, q) for t, q in points if t > start_min]]

        if points[-1][0] < end_min:
            points = [*points, (end_min, points[-1][1])]

        intervals: list[tuple[float, int]] = []
        total_area = 0.0
        peak = 0
        for i in range(len(points) - 1):
            t0, q0 = points[i]
            t1, _ = points[i + 1]
            seg_start = max(t0, start_min)
            seg_end = min(t1, end_min)
            if seg_end <= seg_start:
                continue
            duration = seg_end - seg_start
            total_area += duration * q0
            intervals.append((duration, q0))
            peak = max(peak, q0)

        total_duration = end_min - start_min
        avg = total_area / total_duration if total_duration > 0 else 0.0
        if not intervals:
            return round(avg, 6), peak, 0.0

        threshold = 0.95 * sum(duration for duration, _ in intervals)
        cumulative = 0.0
        p95 = 0.0
        for duration, q in sorted(intervals, key=lambda item: (item[1], item[0])):
            cumulative += duration
            p95 = float(q)
            if cumulative >= threshold:
                break

        return round(avg, 6), peak, round(p95, 6)

    def compute_queue_metrics(self, warmup_time_min: float, end_min: float) -> dict[str, float | int]:
        """Возвращает агрегаты очереди по post-warmup timeline."""
        avg, peak, p95 = self._weighted_queue_metrics(self._queue_timeline, warmup_time_min, end_min)
        return {
            "avg_queue_length": avg,
            "max_queue_length": peak,
            "p95_queue_length": p95,
        }

    def compute_sla_metrics(self, tasks: Optional[list[Task]] = None) -> dict:
        """Рассчитывает SLA-метрики по завершённым заданиям."""
        source = tasks if tasks is not None else self._completed_tasks
        plan_tasks = [t for t in source if t.urgency_class == UrgencyClass.PLAN and t.done_at]
        sla_plan_target = self._sla_fraction(
            plan_tasks,
            lambda t: (t.done_at - t.arrived_at).total_seconds() / _SECONDS_PER_HOUR <= self._target_hours,
        )
        sla_plan_max = self._sla_fraction(
            plan_tasks,
            lambda t: (t.done_at - t.arrived_at).total_seconds() / _SECONDS_PER_HOUR <= self._max_hours,
        )
        cito_total = len(self._cito_assignments) + self._cito_not_assigned
        cito_ok = sum(
            1 for (t_arr, t_assign) in self._cito_assignments.values()
            if (t_assign - t_arr).total_seconds() / _SECONDS_PER_HOUR
            <= self._cito_epsilon_h
        )
        sla_cito = cito_ok / cito_total if cito_total > 0 else 1.0
        return {
            "SLA_CITO_target": round(sla_cito, 4),
            "SLA_plan_target": round(sla_plan_target, 4),
            "SLA_plan_max": round(sla_plan_max, 4),
        }

    @staticmethod
    def _sla_fraction(tasks: list[Task], condition: Callable) -> float:
        if not tasks:
            return 1.0
        ok = sum(1 for t in tasks if condition(t))
        return ok / len(tasks)

    def compute_load_variance(self, doctors: list[Doctor], period_hours: float = 8.0) -> float:
        """Онлайн-приближение дисперсии нагрузки."""
        if not doctors:
            return 0.0
        rho = []
        for d in doctors:
            if period_hours > 0 and d.productivity_rate > 0:
                rho_q = d.current_load / (d.productivity_rate * period_hours)
            else:
                rho_q = 0.0
            rho.append(rho_q)
        k = len(rho)
        rho_mean = sum(rho) / k
        variance = sum((r - rho_mean) ** 2 for r in rho) / k
        return round(variance, 6)

    def compute_final_variance(self, doctors: list[Doctor], period_hours: float = 8.0) -> float:
        """Финальный расчёт дисперсии нагрузки по завершённым заданиям."""
        if not doctors or period_hours <= 0:
            return 0.0
        work: dict[str, float] = defaultdict(float)
        for task in self._completed_tasks:
            if task.assigned_to and task.complexity:
                work[str(task.assigned_to)] += task.complexity
        rho = []
        for d in doctors:
            if d.productivity_rate > 0:
                total_work = work.get(str(d.id), 0.0)
                rho.append(total_work / (d.productivity_rate * period_hours))
        if not rho:
            return 0.0
        k = len(rho)
        rho_mean = sum(rho) / k
        variance = sum((r - rho_mean) ** 2 for r in rho) / k
        return round(variance, 6)

    def estimate_tat(self, task: Task, queue_state: list[Task], doctors: list[Doctor]) -> float:
        """Оценивает время выполнения задания в часах."""
        compatible = [d for d in doctors if task.modality in d.specializations]
        if not compatible:
            return self._max_hours
        best = min(compatible, key=lambda d: d.current_load / d.productivity_rate)
        service_time_h = task.complexity / best.productivity_rate
        position = sum(
            1 for j in queue_state
            if j.id != task.id
            and j.urgency_class != UrgencyClass.CITO
            and j.modality in best.specializations
        )
        w_q_h = position * service_time_h
        return w_q_h + service_time_h

    def check_sla_violations(
        self,
        t: datetime,
        queue_state: list[Task],
        doctors: Optional[list[Doctor]] = None,
    ) -> list[dict]:
        """
        Проверяет SLA для всех заданий в Q(t).
        Генерирует события SLA_WARNING и SLA_VIOLATION через publish().
        Возвращает список событий.

        Args:
            t:           текущий момент времени
            queue_state: задания в очереди
            doctors:     пул врачей. Если передан, используется каноническое
                         предиктивное правило SLA_WARNING: elapsed + estimated.
                         Если не передан — degraded mode: fallback на elapsed_h.
        """
        events = []
        warning_threshold_h = self._target_hours * self._warning_threshold

        for task in queue_state:
            elapsed_h = (t - task.arrived_at).total_seconds() / _SECONDS_PER_HOUR
            remaining_h = (task.deadline_target - t).total_seconds() / _SECONDS_PER_HOUR
            deadline_max_exceeded = t > task.deadline_max

            if deadline_max_exceeded and task.state in (TaskState.QUEUED, TaskState.ASSIGNED):
                event = {
                    "type": "SLA_VIOLATION",
                    "task_id": task.id,
                    "triggered_at": t.isoformat(),
                    "deadline_exceeded_by_h": (
                        (t - task.deadline_max).total_seconds() / _SECONDS_PER_HOUR
                    ),
                    "current_state": task.state,
                }
                events.append(event)
                self.publish("SLA_VIOLATION", task=task, t=t)

            elif task.state in (TaskState.QUEUED, TaskState.ASSIGNED):
                if doctors:
                    estimated_tat_h = self.estimate_tat(task, queue_state, doctors)
                    trigger_warning = (elapsed_h + estimated_tat_h) >= warning_threshold_h
                else:
                    trigger_warning = elapsed_h >= warning_threshold_h

                if trigger_warning:
                    event = {
                        "type": "SLA_WARNING",
                        "task_id": task.id,
                        "triggered_at": t.isoformat(),
                        "time_to_deadline_h": remaining_h,
                    }
                    events.append(event)
                    self.publish("SLA_WARNING", task=task, t=t)

        return events

    def get_metrics(
        self, queue_state: list[Task], doctors: list[Doctor]
    ) -> MetricsSnapshot:
        snap = MetricsSnapshot()
        snap.queue_depth = len(queue_state)
        by_mod: dict[str, int] = defaultdict(int)
        for t in queue_state:
            by_mod[t.modality] += 1
        snap.queue_by_modality = dict(by_mod)
        snap.online_load_variance = self.compute_load_variance(doctors)
        snap.sigma_w2_final = self.compute_final_variance(doctors) if self._completed_tasks else 0.0
        # устаревший алиас для клиентов
        snap.load_variance = snap.sigma_w2_final if self._completed_tasks else snap.online_load_variance
        sla = self.compute_sla_metrics()
        snap.sla_cito_target = sla["SLA_CITO_target"]
        snap.sla_plan_target = sla["SLA_plan_target"]
        snap.sla_plan_max = sla["SLA_plan_max"]
        snap.doctors_load = [
            {
                "doctor_id": str(d.id),
                "current_load": d.current_load,
                "normalized_load": d.current_load / d.productivity_rate,
                "is_available": d.is_available,
            }
            for d in doctors
        ]
        return snap

    def get_queue_depth_by_modality(self, queue_state: list[Task]) -> dict[str, int]:
        result: dict[str, int] = defaultdict(int)
        for t in queue_state:
            result[t.modality] += 1
        return dict(result)
