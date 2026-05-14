"""Имитационная модель для экспериментального контура."""
from __future__ import annotations

import heapq
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import simpy

_SIM_BASE_DT = datetime(2025, 1, 1, 0, 0, 0)

from algorithms.base import AlgorithmConfig
from algorithms.factory import PrioritizerFactory
from core.assignment_engine import AssignmentEngine
from core.audit_logger import AuditLogger
from core.metrics_collector import MetricsCollector
from simulation.generators import (
    SimDoctor,
    SimTask,
    arrival_process,
    generate_doctor_pool,
    make_doctors_from_config,
)

_SECONDS_PER_HOUR = 3600.0
_MIN_PER_HOUR = 60.0
_POLL_INTERVAL_MIN = 0.5


class _NoopAuditLogger:
    """Заглушка audit-логера."""

    def log_event_sync(self, *args, **kwargs) -> None:
        return None

    def flush(self) -> None:
        return None


@dataclass
class SimulationResult:
    """Результат одного прогона."""
    algorithm: str
    seed: int
    days: float
    arrival_rate: float
    scenario: str = ""
    assignment_strategy: str = "wll"
    doctor_source: str = "unknown"

    sla_cito_target: float = 0.0
    sla_plan_target: float = 0.0
    sla_plan_max: float = 0.0

    sigma_w2_final: float = 0.0

    median_tat_min: float = 0.0
    mean_tat_min: float = 0.0
    mean_wait_min: float = 0.0
    tat_p25_min: float = 0.0
    tat_p50_min: float = 0.0
    tat_p75_min: float = 0.0
    tat_p95_min: float = 0.0
    rho_avg: float = 0.0
    rho_normalized: float = 0.0
    throughput_per_hour: float = 0.0
    avg_queue_length: float = 0.0
    max_queue_length: int = 0
    p95_queue_length: float = 0.0

    assignment_sequence: list = field(default_factory=list)

    total_tasks: int = 0
    completed_tasks: int = 0
    warmup_tasks: int = 0
    warmup_time_min: float = 0.0
    sla_violations: int = 0
    cito_escalated: int = 0
    cito_not_assigned: int = 0
    cito_total_arrived: int = 0
    plan_sample_size: int = 0
    cito_sample_size: int = 0
    tat_sample_size: int = 0
    valid_plan_sample: bool = False
    valid_cito_sample: bool = False
    valid_tat_sample: bool = False

    num_doctors: int = 0
    doctors_by_modality: dict = field(default_factory=dict)

    mmc_analytic_mean_wait_min: float = 0.0
    mmc_erlang_c: float = 0.0
    mmc_wait_rel_error_pct: float = 0.0

    def to_jsonl_record(self) -> dict:
        """Формат JSONL-вывода для экспериментов."""
        rec = {
            "scenario": self.scenario,
            "algorithm": self.algorithm,
            "assignment_strategy": self.assignment_strategy,
            "doctor_source": self.doctor_source,
            "seed": self.seed,
            "arrival_rate": self.arrival_rate,
            "arrival_rate_per_day": self.arrival_rate,
            "num_doctors": self.num_doctors,
            "doctors_by_modality": self.doctors_by_modality,
            "sla_cito": round(self.sla_cito_target, 4),
            "sla_plan_target": round(self.sla_plan_target, 4),
            "sla_plan_max": round(self.sla_plan_max, 4),
            "sigma_w2": round(self.sigma_w2_final, 6),
            "rho_avg": round(self.rho_avg, 4),
            "rho_normalized": round(self.rho_normalized, 4),
            "tat_median_min": round(self.median_tat_min, 2),
            "tat_mean_min": round(self.mean_tat_min, 2),
            "tat_p25_min": round(self.tat_p25_min, 2),
            "tat_p50_min": round(self.tat_p50_min, 2),
            "tat_p75_min": round(self.tat_p75_min, 2),
            "tat_p95_min": round(self.tat_p95_min, 2),
            "mean_wait_min": round(self.mean_wait_min, 2),
            "throughput_per_hour": round(self.throughput_per_hour, 2),
            "avg_queue_length": round(self.avg_queue_length, 6),
            "max_queue_length": self.max_queue_length,
            "p95_queue_length": round(self.p95_queue_length, 6),
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "warmup_tasks": self.warmup_tasks,
            "warmup_time_min": round(self.warmup_time_min, 2),
            "sla_violations": self.sla_violations,
            "cito_escalated": self.cito_escalated,
            "cito_not_assigned": self.cito_not_assigned,
            "cito_total_arrived": self.cito_total_arrived,
            "plan_sample_size": self.plan_sample_size,
            "cito_sample_size": self.cito_sample_size,
            "tat_sample_size": self.tat_sample_size,
            "valid_plan_sample": self.valid_plan_sample,
            "valid_cito_sample": self.valid_cito_sample,
            "valid_tat_sample": self.valid_tat_sample,
            "assignment_sequence": self.assignment_sequence,
        }

        rec.update({
            "algo": self.algorithm,
            "SLA_CITO_target": round(self.sla_cito_target, 4),
            "SLA_plan_target": round(self.sla_plan_target, 4),
            "SLA_plan_max": round(self.sla_plan_max, 4),
            "load_variance": round(self.sigma_w2_final, 6),
            "median_TAT_min": round(self.median_tat_min, 2),
            "mean_TAT_min": round(self.mean_tat_min, 2),
            "TAT_p95_min": round(self.tat_p95_min, 2),
        })
        if self.scenario == "mmc-validation":
            rec["mmc_analytic_mean_wait_min"] = round(self.mmc_analytic_mean_wait_min, 4)
            rec["mmc_erlang_C"] = round(self.mmc_erlang_c, 6)
            rec["mmc_wait_rel_error_pct"] = round(self.mmc_wait_rel_error_pct, 4)
        return rec


class _SimQueueAdapter:
    """Адаптер SimTask для IPrioritizer.sort()."""
    def __init__(self, sim_task: SimTask) -> None:
        self._t = sim_task

    def __getattr__(self, name):
        return getattr(self._t, name)

    @property
    def arrived_at(self) -> datetime:
        return _SIM_BASE_DT + timedelta(minutes=self._t.arrived_at)

    @property
    def deadline_target(self) -> datetime:
        return _SIM_BASE_DT + timedelta(minutes=self._t.deadline_target)

    @property
    def deadline_max(self) -> datetime:
        return _SIM_BASE_DT + timedelta(minutes=self._t.deadline_max)


class Simulator:
    """SimPy-имитационная модель."""

    def __init__(
        self,
        algorithm_type: str,
        params: AlgorithmConfig,
        seed: int,
        config: dict,
        jsonl_path: Optional[str] = None,
        audit_mode: str = "full",
        num_doctors_override: Optional[int] = None,
        scenario: str = "",
        assignment_strategy: str = "wll",
        allow_synthetic: bool = False,
    ) -> None:
        self.rng = random.Random(seed)
        self.seed = seed
        self.algorithm_type = algorithm_type
        self.params = params
        self.config = config
        self.scenario = scenario
        self.audit_mode = audit_mode
        self._sim_tie_break_mode = config.get("simulation", {}).get("sim_tie_break", "deterministic")
        self.assignment_strategy = assignment_strategy
        self._rr_index: int = 0

        self.prioritizer = PrioritizerFactory.create(algorithm_type, params)
        self.assignment_engine = AssignmentEngine()
        self._queue_metrics = MetricsCollector(
            target_hours=config.get("sla", {}).get("target_hours", 2.0),
            max_hours=config.get("sla", {}).get("max_hours", 24.0),
            cito_assign_epsilon_sec=config.get("sla", {}).get("cito_assign_epsilon_sec", 5.0),
        )

        self.env = simpy.Environment()
        self.env.task_buffer = []
        self.env.new_work = self.env.event()
        self._queue: dict[uuid.UUID, SimTask] = {}
        self._deadline_heap: list[tuple[float, uuid.UUID]] = []
        self._sla_monitor_proc: Optional[object] = None
        self._mode = config.get("simulation", {}).get("mode", "evaluation")
        doctors, doctor_source = make_doctors_from_config(
            config,
            self.rng,
            mode=self._mode,
            allow_synthetic=allow_synthetic,
        )
        if num_doctors_override is not None:
            if doctor_source == "synthetic_pool":
                doctors = generate_doctor_pool(config, self.rng, num_doctors_override)
            else:
                doctors = self._resize_doctors(doctors, num_doctors_override)
        self._doctors: list[SimDoctor] = doctors
        self.doctor_source = doctor_source
        self._doctor_source = doctor_source

        sim_cfg = config.get("simulation", {})
        self._task_gen_cfg: dict = sim_cfg.get("task_generation", {})
        if scenario in ("validation",):
            self._hourly_profile: Optional[list] = None
        elif scenario == "mmc-validation":
            self._hourly_profile = [1.0] * 8
        else:
            self._hourly_profile: Optional[list] = sim_cfg.get("hourly_profile")

        self._warmup_tasks: int = sim_cfg.get("warmup_tasks", 0)
        self._warmup_time_min: float = float(sim_cfg.get("warmup_time_min", 0.0))

        if scenario == "mmc-validation":
            mmc_cfg = sim_cfg.get("mmc_validation", {})
            c = int(mmc_cfg.get("num_servers", 9))
            mu = float(mmc_cfg.get("mu_per_hour", 7.0))
            self._doctors = [
                SimDoctor(
                    id=f"mmc_{i + 1:03d}",
                    specializations=["ECG_REST"],
                    productivity_rate=mu,
                )
                for i in range(c)
            ]
            self._task_gen_cfg = {
                "modality_weights": {"ECG_REST": 1.0},
                "complexity_base": {"ECG_REST": 1.0},
                "complexity_spread": 0.0,
                "cito_probability": 0.0,
            }
            wt_m = mmc_cfg.get("warmup_tasks")
            if wt_m is not None:
                self._warmup_tasks = int(wt_m)
            wtm = mmc_cfg.get("warmup_time_min")
            if wtm is not None:
                self._warmup_time_min = float(wtm)
        # Для cito-burst прогрев отключается, чтобы не терять статистику короткого сценария.
        if scenario == "cito-burst":
            self._warmup_tasks = 0
            self._warmup_time_min = 0.0
        self._tasks_completed: int = 0

        # Статистика (накапливается только после прогрева)
        self._tat_list: list[float] = []
        self._wait_list: list[float] = []
        self._plan_done: list[bool] = []
        self._plan_max_done: list[bool] = []
        self._cito_assign_delays: list[float] = []
        self._cito_not_assigned: int = 0
        self._cito_total_arrived: int = 0
        self._assignment_sequence: list[tuple] = []
        self._sla_violations: int = 0
        self._cito_escalated: int = 0
        self._doctor_work: dict[str, float] = {d.id: 0.0 for d in self._doctors}

        # AuditLogger (только JSONL в симуляторе — без БД)
        if self.audit_mode == "none":
            self.audit = _NoopAuditLogger()
        else:
            self.audit = AuditLogger(jsonl_path=jsonl_path or "results/sim_audit.jsonl")

        # SLA-параметры из config
        sla_cfg = config.get("sla", {})
        self._target_min = sla_cfg.get("target_hours", 2.0) * _MIN_PER_HOUR
        self._max_min = sla_cfg.get("max_hours", 24.0) * _MIN_PER_HOUR

    def _make_arrival_process(self, lambda_per_min: float):
        return arrival_process(
            self.env,
            lambda_per_min,
            self.rng,
            sla_params=self.config.get("sla", {}),
            task_gen_cfg=self._task_gen_cfg,
            hourly_profile=self._hourly_profile,
        )

    def _current_queue_len(self) -> int:
        return sum(1 for task in self._queue.values() if task.state in ("QUEUED", "ESCALATED"))

    def _record_queue_length(self, now_min: float) -> None:
        current_len = self._current_queue_len()
        self._queue_metrics.record_queue_length(now_min, current_len)

    def run(self, duration_min: float) -> SimulationResult:
        """Запуск имитации на duration_min симуляционных минут."""
        arrival_rate_per_day = self.config.get("simulation", {}).get("baseline_arrival_rate", 446)
        lambda_per_min = arrival_rate_per_day / (8 * _MIN_PER_HOUR)

        self.env.process(self._make_arrival_process(lambda_per_min))
        # monitor до dispatch, чтобы dispatch мог Interrupt при появлении более раннего дедлайна
        self._sla_monitor_proc = self.env.process(self._sla_monitor_process())
        self.env.process(self._dispatch_process())

        self.env.run(until=duration_min)
        return self.collect_results(duration_min, arrival_rate_per_day)

    def run_with_rate(self, duration_min: float, arrival_rate_per_day: float) -> SimulationResult:
        """Запуск с явно заданной интенсивностью потока."""
        if self.scenario == "validation":
            return self._run_validation()
        if self._doctors:
            mu_avg = sum(d.productivity_rate for d in self._doctors) / len(self._doctors)
            lambda_h = arrival_rate_per_day / 8.0
            n_doctors = len(self._doctors)
            rho_norm = lambda_h / (n_doctors * mu_avg) if mu_avg > 0 and n_doctors > 0 else 0.0
            n_min_theory = math.ceil(lambda_h / mu_avg) if mu_avg > 0 else 0
            print(
                f"[calibration] lambda={arrival_rate_per_day:.2f}/day "
                f"lambda_h={lambda_h:.2f}/h | mu_avg={mu_avg:.2f}/h | "
                f"N={n_doctors} | rho={rho_norm:.3f} | "
                f"N_min_theory={n_min_theory}"
            )
        lambda_per_min = arrival_rate_per_day / (8 * _MIN_PER_HOUR)
        self.env.process(self._make_arrival_process(lambda_per_min))
        self._sla_monitor_proc = self.env.process(self._sla_monitor_process())
        self.env.process(self._dispatch_process())
        self.env.run(until=duration_min)
        return self.collect_results(duration_min, arrival_rate_per_day)

    def _run_validation(self) -> SimulationResult:
        """Валидационный сценарий с фиксированным набором задач и одним врачом."""
        from simulation.generators import SimDoctor as _SD

        val_rng = random.Random(self.seed)
        doc_val = _SD(id="doc_val", specializations=["ECG_REST"], productivity_rate=6.0)
        self._doctors = [doc_val]
        self._doctor_work = {doc_val.id: 0.0}
        self._warmup_tasks = 0

        def _inject(env):
            for i in range(20):
                t_arrive = float(i * 5)
                delay = t_arrive - env.now
                if delay > 0:
                    yield env.timeout(delay)
                task = SimTask(
                    id=uuid.UUID(int=val_rng.getrandbits(128), version=4),
                    external_id=f"val-{i:03d}",
                    modality="ECG_REST",
                    urgency_class="план",
                    complexity=1.0,
                    arrived_at=t_arrive,
                    deadline_target=t_arrive + 120.0,
                    deadline_max=t_arrive + 1440.0,
                )
                env.task_buffer.append(task)
                if not env.new_work.triggered:
                    env.new_work.succeed()

        duration_min = 19 * 5 + 300.0
        self.env.process(_inject(self.env))
        self.env.process(self._dispatch_process())
        self.env.run(until=duration_min)
        return self.collect_results(duration_min, 0.0)

    def _inject_cito_burst(
        self,
        n_tasks: int = 15,
        start_min: float = 240.0,
        interval_min: float = 4.0,
        duration_min: Optional[float] = None,
    ):
        """Добавляет в среду детерминированный всплеск CITO-задач."""
        if duration_min is not None and duration_min > 0 and interval_min > 0:
            n_tasks = max(n_tasks, int(duration_min // interval_min))

        def _burst(env):
            for i in range(n_tasks):
                yield env.timeout(start_min + i * interval_min - env.now if i == 0 else interval_min)
                task_id = uuid.UUID(int=self.rng.getrandbits(128), version=4)
                now = env.now
                cito_task = SimTask(
                    id=task_id,
                    external_id=f"cito-burst-{i:03d}",
                    modality="ECG_REST",
                    urgency_class="CITO",
                    complexity=1.0,
                    arrived_at=now,
                    deadline_target=now + self._target_min,
                    deadline_max=now + self._max_min,
                )
                env.task_buffer.append(cito_task)
                if not env.new_work.triggered:
                    env.new_work.succeed()
                self.audit.log_event_sync(
                    event_type="CITO_BURST_INJECT",
                    task_id=task_id,
                    payload={"at_min": now, "burst_index": i},
                )

        self.env.process(_burst(self.env))

    def collect_results(self, duration_min: float, arrival_rate: float) -> SimulationResult:
        """Агрегирует результаты прогона."""
        n = len(self._tat_list)
        result = SimulationResult(
            algorithm=self.algorithm_type,
            scenario=self.scenario,
            assignment_strategy=self.assignment_strategy,
            doctor_source=self._doctor_source,
            seed=self.seed,
            days=duration_min / (8 * _MIN_PER_HOUR),
            arrival_rate=arrival_rate,
            total_tasks=self._tasks_completed + len(self._queue),
            completed_tasks=n,
            warmup_tasks=min(self._warmup_tasks, self._tasks_completed),
            warmup_time_min=self._warmup_time_min,
            sla_violations=self._sla_violations,
            cito_escalated=self._cito_escalated,
            cito_not_assigned=self._cito_not_assigned,
            cito_total_arrived=self._cito_total_arrived,
            plan_sample_size=len(self._plan_done),
            cito_sample_size=self._cito_total_arrived,
            tat_sample_size=n,
            valid_plan_sample=len(self._plan_done) > 0,
            valid_cito_sample=self._cito_total_arrived > 0,
            valid_tat_sample=n > 0,
            assignment_sequence=list(self._assignment_sequence),
        )
        queue_metrics = self._queue_metrics.compute_queue_metrics(self._warmup_time_min, duration_min)
        result.avg_queue_length = float(queue_metrics["avg_queue_length"])
        result.max_queue_length = int(queue_metrics["max_queue_length"])
        result.p95_queue_length = float(queue_metrics["p95_queue_length"])
        if n > 0:
            sorted_tat = sorted(self._tat_list)
            result.median_tat_min = sorted_tat[n // 2]
            result.mean_tat_min = sum(self._tat_list) / n
            result.throughput_per_hour = n / (duration_min / _MIN_PER_HOUR)
            p25_idx = min(int(0.25 * n), n - 1)
            p50_idx = min(int(0.50 * n), n - 1)
            p75_idx = min(int(0.75 * n), n - 1)
            p95_idx = min(int(0.95 * n), n - 1)
            result.tat_p25_min = sorted_tat[p25_idx]
            result.tat_p50_min = sorted_tat[p50_idx]
            result.tat_p75_min = sorted_tat[p75_idx]
            result.tat_p95_min = sorted_tat[p95_idx]
            result.mean_wait_min = sum(self._wait_list) / len(self._wait_list) if self._wait_list else 0.0
        if result.valid_plan_sample:
            result.sla_plan_target = sum(self._plan_done) / len(self._plan_done)
        if self._plan_max_done:
            result.sla_plan_max = sum(self._plan_max_done) / len(self._plan_max_done)
        cito_epsilon_sec = self.config.get("sla", {}).get("cito_assign_epsilon_sec", 5.0)
        cito_epsilon_min = cito_epsilon_sec / 60.0
        cito_total = result.cito_total_arrived
        if result.valid_cito_sample:
            cito_ok = sum(1 for d in self._cito_assign_delays if d <= cito_epsilon_min)
            result.sla_cito_target = cito_ok / cito_total
        result.sigma_w2_final = self._compute_load_variance(duration_min)
        result.rho_avg = self._compute_rho_avg(duration_min, arrival_rate)
        result.rho_normalized = self._compute_rho_normalized(arrival_rate)
        result.num_doctors = len(self._doctors)
        modality_counts: dict[str, int] = {}
        for doc in self._doctors:
            for spec in doc.specializations:
                modality_counts[spec] = modality_counts.get(spec, 0) + 1
        result.doctors_by_modality = modality_counts

        if self.scenario == "mmc-validation" and self._doctors:
            from simulation.mmc_analytic import erlang_c_wait_metrics

            c = len(self._doctors)
            mu_h = self._doctors[0].productivity_rate
            lam_h = arrival_rate / 8.0
            p_wait, wq_h, _ = erlang_c_wait_metrics(c, lam_h, mu_h)
            wq_min_ana = wq_h * _MIN_PER_HOUR
            result.mmc_analytic_mean_wait_min = wq_min_ana
            result.mmc_erlang_c = p_wait
            if math.isfinite(wq_min_ana) and wq_min_ana > 1e-9:
                result.mmc_wait_rel_error_pct = (
                    100.0 * abs(result.mean_wait_min - wq_min_ana) / wq_min_ana
                )
        self.audit.flush()
        return result

    def _dispatch_process(self):
        """Цикл диспетчеризации в среде SimPy."""
        while True:
            while self.env.task_buffer:
                task = self.env.task_buffer.pop(0)
                self._queue[task.id] = task
                if task.urgency_class == "CITO":
                    self._cito_total_arrived += 1
                prev_min = self._deadline_heap[0][0] if self._deadline_heap else None
                heapq.heappush(self._deadline_heap, (task.deadline_max, task.id))
                if (
                    self._sla_monitor_proc is not None
                    and (prev_min is None or task.deadline_max < prev_min)
                ):
                    self._sla_monitor_proc.interrupt()
                arrived_iso = (
                    _SIM_BASE_DT + timedelta(minutes=task.arrived_at)
                ).isoformat()
                self.audit.log_event_sync(
                    event_type="RECEIVED",
                    task_id=task.id,
                    algorithm_used=self.algorithm_type,
                    payload={
                        "modality": task.modality,
                        "urgency_class": task.urgency_class,
                        "arrived_at_min": task.arrived_at,
                        "arrived_at": arrived_iso,
                    },
                )
                self._record_queue_length(self.env.now)

            assigned_any = False
            while True:
                result = self._select_next(self.env.now)
                if result is None:
                    break
                sim_task, sim_doc, prio_val, q_size = result
                self._do_assign(sim_task, sim_doc, self.env.now, prio_val, q_size)
                self.env.process(self._service_process(sim_task, sim_doc))
                assigned_any = True

            self._cito_check(self.env.now)

            yield self.env.any_of(
                [self.env.new_work, self.env.timeout(_POLL_INTERVAL_MIN)]
            )
            if self.env.new_work.triggered:
                self.env.new_work = self.env.event()

    def _select_next(self, sim_now: float):
        """task-first выбор (j*, q*). Возвращает (task, doctor, priority_value, queue_size)."""
        queue_size = 0
        escalated_eligible: list[SimTask] = []
        queued_eligible: list[SimTask] = []

        # Модальности, которые сейчас может обслужить хотя бы один свободный врач
        available_modalities: set[str] = set()
        for d in self._doctors:
            if d.is_available and not d.is_outage:
                available_modalities.update(d.specializations)

        if not available_modalities:
            return None

        # Одним проходом собираем (1) размер очереди для метрики и (2) только выполнимые задания
        for t in self._queue.values():
            if t.state not in ("QUEUED", "ESCALATED"):
                continue
            queue_size += 1
            if t.modality not in available_modalities:
                continue
            if t.state == "ESCALATED":
                escalated_eligible.append(t)
            else:
                queued_eligible.append(t)

        if queue_size == 0:
            return None
        if not escalated_eligible and not queued_eligible:
            return None

        # 1) Эскалированные задачи: самый ранний escalated_at (с фильтром доступности по модальности)
        if escalated_eligible:
            j_star = min(escalated_eligible, key=lambda t: t.escalated_at or 0.0)
            doc = self._find_doctor_sim(j_star)
            if doc is None:
                return None
            return (j_star, doc, 0.0, queue_size)

        # 2) Иначе: сортируем только по выполнимым (queued) заданиям
        if not queued_eligible:
            return None

        t_dt = _SIM_BASE_DT + timedelta(minutes=sim_now)
        adapted = [_SimQueueAdapter(t) for t in queued_eligible]
        sorted_adapted = self.prioritizer.sort(adapted, t_dt, self.params)
        if not sorted_adapted:
            return None

        # На случай, если приоритетная задача по сортировке окажется невыполнимой — пробуем дальше по списку
        for adapted_item in sorted_adapted:
            j_star = adapted_item._t
            doc = self._find_doctor_sim(j_star)
            if doc is None:
                continue
            priority_value = 0.0
            try:
                priority_value = self.prioritizer.compute_priority(adapted_item, t_dt, self.params)
            except Exception:
                pass
            return (j_star, doc, priority_value, queue_size)

        return None

    def _find_doctor_sim(self, task: SimTask) -> Optional[SimDoctor]:
        """Выбор врача по текущей стратегии."""
        if self.assignment_strategy == "round-robin":
            return self._find_doctor_rr(task)
        return self._find_doctor_wll(task)

    def _find_doctor_wll(self, task: SimTask) -> Optional[SimDoctor]:
        """WLL-выбор врача с минимальной нормированной нагрузкой."""
        eligible = [
            d for d in self._doctors
            if d.is_available and not d.is_outage
            and task.modality in d.specializations
        ]
        if not eligible:
            return None
        min_score = min(d.current_load / d.productivity_rate for d in eligible)
        equal_candidates = [
            d for d in eligible
            if abs((d.current_load / d.productivity_rate) - min_score) < 1e-12
        ]
        if len(equal_candidates) == 1:
            return equal_candidates[0]

        if self._sim_tie_break_mode == "rng":
            return self.rng.choice(equal_candidates)

        return min(equal_candidates, key=lambda d: d.id)

    def _find_doctor_rr(self, task: SimTask) -> Optional[SimDoctor]:
        """Циклический выбор доступного врача с совместимой специализацией."""
        eligible = [
            d for d in self._doctors
            if d.is_available and not d.is_outage
            and task.modality in d.specializations
        ]
        if not eligible:
            return None
        idx = self._rr_index % len(eligible)
        self._rr_index = (self._rr_index + 1) % len(self._doctors)
        return eligible[idx]

    def _is_post_warmup(self, now_min: float) -> bool:
        """Единое условие включения наблюдения в итоговую статистику."""
        return (self._tasks_completed >= self._warmup_tasks) and (now_min >= self._warmup_time_min)

    def _do_assign(
        self,
        task: SimTask,
        doc: SimDoctor,
        sim_now: float,
        priority_value: float = 0.0,
        queue_size: int = 0,
    ) -> None:
        task.state = "ASSIGNED"
        task.assigned_to = doc.id
        doc.current_load += task.complexity
        doc.is_available = False
        assign_delay_min = sim_now - task.arrived_at
        if task.urgency_class == "CITO":
            self._cito_assign_delays.append(assign_delay_min)
        self._assignment_sequence.append((str(task.id), doc.id, sim_now))
        self.audit.log_event_sync(
            event_type="ASSIGNED",
            task_id=task.id,
            actor=doc.id,
            algorithm_used=self.algorithm_type,
            payload={
                "doctor_id": doc.id,
                "queue_wait_min": assign_delay_min,
                "priority_value": round(priority_value, 6),
                "queue_size_at_assignment": queue_size,
                "sim_time_min": sim_now,
                "arrived_at_min": task.arrived_at,
                "deadline_target_min": task.deadline_target,
                "assigned_to_worker": doc.id,
            },
        )
        self._record_queue_length(sim_now)

    def _service_process(self, task: SimTask, doc: SimDoctor):
        """Процесс обслуживания задания врачом."""
        task.state = "IN_PROGRESS"
        task.started_at = self.env.now
        tau_h = self.rng.expovariate(doc.productivity_rate / task.complexity)
        tau_min = tau_h * _MIN_PER_HOUR
        yield self.env.timeout(tau_min)

        task.state = "DONE"
        task.done_at = self.env.now
        doc.current_load = max(0.0, doc.current_load - task.complexity)
        if not doc.is_outage:
            doc.is_available = True
        if not self.env.new_work.triggered:
            self.env.new_work.succeed()
        self._doctor_work[doc.id] = self._doctor_work.get(doc.id, 0.0) + task.complexity

        self._tasks_completed += 1
        tat_min = task.done_at - task.arrived_at

        # Исключаем прогрев по числу задач и по времени симуляции.
        if not self._is_post_warmup(self.env.now):
            self._queue.pop(task.id, None)
            return

        self._tat_list.append(tat_min)
        self._wait_list.append(task.started_at - task.arrived_at)
        if task.urgency_class == "план":
            self._plan_done.append(tat_min <= self._target_min)
            self._plan_max_done.append(tat_min <= self._max_min)

        self.audit.log_event_sync(
            event_type="DONE",
            task_id=task.id,
            actor=doc.id,
            algorithm_used=self.algorithm_type,
            payload={
                "TAT": round(tat_min, 2),
                "sla_target_met": tat_min <= self._target_min,
                "sla_max_met": tat_min <= self._max_min,
                "complexity": task.complexity,
                "duration_h": tau_h,
            },
        )
        # Убрать из очереди
        self._queue.pop(task.id, None)

    def _sla_monitor_process(self):
        """Эскалации SLA по событиям: следующий дедлайн хранится в heap.

        Это убирает дорогой полный перебор очереди каждую симуляционную минуту.
        """
        while True:
            try:
                if not self._deadline_heap:
                    # Нет задач в heap — ждём появление новых через dispatch
                    yield self.env.timeout(1.0)
                    continue

                next_deadline_min, _ = self._deadline_heap[0]
                now = self.env.now

                # Если дедлайн наступил — обрабатываем пачкой
                if next_deadline_min <= now:
                    while self._deadline_heap and self._deadline_heap[0][0] <= now:
                        _, task_id = heapq.heappop(self._deadline_heap)
                        task = self._queue.get(task_id)
                        if not task or task.state not in ("QUEUED", "ASSIGNED"):
                            continue
                        if now >= task.deadline_max:
                            self._sla_violations += 1
                            task.state = "ESCALATED"
                            task.escalated_at = now
                            self.audit.log_event_sync(
                                event_type="SLA_VIOLATION",
                                task_id=task_id,
                                payload={"triggered_at_min": now},
                            )
                            self._record_queue_length(now)
                    continue

                # Иначе ждём до ближайшего дедлайна
                yield self.env.timeout(next_deadline_min - now)
            except simpy.Interrupt:
                # dispatch добавил более ранний дедлайн => пересчитаем next_deadline
                continue

    def _cito_check(self, sim_now: float) -> None:
        """Эскалирует CITO-задания без доступного врача после batch-назначений."""
        for task in list(self._queue.values()):
            if task.state == "QUEUED" and task.urgency_class == "CITO":
                if self._find_doctor_sim(task) is None:
                    task.state = "ESCALATED"
                    task.escalated_at = sim_now
                    self._cito_escalated += 1
                    self._cito_not_assigned += 1
                    self.audit.log_event_sync(
                        event_type="CITO_ESCALATED",
                        task_id=task.id,
                        payload={"triggered_at_min": sim_now},
                    )
                    self._record_queue_length(sim_now)

    @staticmethod
    def _resize_doctors(doctors: list[SimDoctor], target_size: int) -> list[SimDoctor]:
        """Изменяет размер явного пула врачей без перехода в synthetic pool."""
        if target_size <= 0:
            raise ValueError("num_doctors_override must be > 0")
        if target_size <= len(doctors):
            return doctors[:target_size]

        resized = list(doctors)
        base = list(doctors)
        i = 0
        while len(resized) < target_size:
            src = base[i % len(base)]
            resized.append(
                SimDoctor(
                    id=f"{src.id}_extra_{i + 1}",
                    specializations=list(src.specializations),
                    productivity_rate=src.productivity_rate,
                )
            )
            i += 1
        return resized

    def _compute_load_variance(self, duration_min: float) -> float:
        """Вычисляет дисперсию нормированной нагрузки по врачам."""
        docs = self._doctors
        if not docs or duration_min <= 0.0:
            return 0.0
        T_h = duration_min / _MIN_PER_HOUR
        rho = []
        for d in docs:
            if d.productivity_rate > 0:
                work = self._doctor_work.get(d.id, 0.0)
                rho.append(work / (d.productivity_rate * T_h))
        if not rho:
            return 0.0
        mean = sum(rho) / len(rho)
        return sum((r - mean) ** 2 for r in rho) / len(rho)

    def _compute_rho_avg(self, duration_min: float, arrival_rate_per_day: float) -> float:
        """Оценивает среднюю загрузку пула врачей."""
        lambda_h = arrival_rate_per_day / 8.0
        sum_mu = sum(d.productivity_rate for d in self._doctors)
        if sum_mu <= 0:
            return 0.0
        # Используем self._task_gen_cfg, чтобы учитывать сценарные параметры генерации.
        cfg = self._task_gen_cfg
        from simulation.generators import (
            _DEFAULT_COMPLEXITY_BASE,
            _DEFAULT_MODALITY_WEIGHTS,
        )
        weights = cfg.get("modality_weights", _DEFAULT_MODALITY_WEIGHTS)
        complexity = cfg.get("complexity_base", _DEFAULT_COMPLEXITY_BASE)
        total_w = sum(weights.values())
        e_s = sum(weights[m] / total_w * complexity.get(m, 1.0) for m in weights)
        return round(lambda_h * e_s / sum_mu, 4)

    def _compute_rho_normalized(self, arrival_rate_per_day: float) -> float:
        """Нормированная загрузка ρ = λ / (N * μ_avg) в задачах/час."""
        n_doctors = len(self._doctors)
        if n_doctors <= 0:
            return 0.0
        mu_avg = sum(d.productivity_rate for d in self._doctors) / n_doctors
        if mu_avg <= 0:
            return 0.0
        arrival_rate_per_hour = arrival_rate_per_day / 8.0
        return round(arrival_rate_per_hour / (n_doctors * mu_avg), 4)
