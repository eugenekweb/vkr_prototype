"""Генераторы задач и пулов врачей для имитационного контура."""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

_SIM_BASE_DT = datetime(2025, 1, 1, 0, 0, 0)

_DEFAULT_MODALITY_WEIGHTS = {
    "ECG_REST": 73.0,
    "HOLTER":   10.0,
    "SMAD":      8.0,
    "ECHO_KG":   5.0,
    "EEG":       3.0,
    "ENMG":      1.0,
}

_DEFAULT_COMPLEXITY_BASE = {
    "ECG_REST": 1.0,
    "HOLTER":   4.0,
    "SMAD":     3.0,
    "ECHO_KG":  8.0,
    "EEG":      3.0,
    "ENMG":     6.0,
}

_DEFAULT_COMPLEXITY_SPREAD: float = 0.20   # ±20%
_DEFAULT_CITO_PROBABILITY: float = 0.008   # 0.8%, только ЭКГ


def _build_modality_tables(weights: dict[str, float]):
    """Нормирует веса модальностей и возвращает (names, probs)."""
    total = sum(weights.values())
    names = sorted(weights.keys())
    probs = [weights[m] / total for m in names]
    return names, probs


@dataclass
class SimTask:
    """Лёгкая версия Task для имитационной модели."""
    id: uuid.UUID
    external_id: str
    modality: str
    urgency_class: str
    complexity: float
    arrived_at: float
    deadline_target: float
    deadline_max: float
    state: str = "QUEUED"
    assigned_to: Optional[str] = None
    started_at: Optional[float] = None
    done_at: Optional[float] = None
    escalated_at: Optional[float] = None
    version: int = 0

    @property
    def arrived_at_dt(self) -> datetime:
        return _SIM_BASE_DT + timedelta(minutes=self.arrived_at)

    @property
    def deadline_target_dt(self) -> datetime:
        return _SIM_BASE_DT + timedelta(minutes=self.deadline_target)

    @property
    def deadline_max_dt(self) -> datetime:
        return _SIM_BASE_DT + timedelta(minutes=self.deadline_max)


@dataclass
class SimDoctor:
    """Лёгкая версия Doctor для имитационной модели."""
    id: str
    specializations: list[str]
    productivity_rate: float
    is_available: bool = True
    current_load: float = 0.0
    is_outage: bool = False

    @property
    def urgency_class(self):
        return None

    def get_complexity_attr(self):
        return self.current_load


def generate_task(
    sim_time_min: float,
    rng: random.Random,
    target_hours: float = 2.0,
    max_hours: float = 24.0,
    task_counter: int = 0,
    task_gen_cfg: Optional[dict] = None,
    cito_probability_override: Optional[float] = None,
) -> SimTask:
    """Генерирует одно задание для симуляции.

    Args:
        sim_time_min:            текущее время в симуляции (минуты)
        rng:                     изолированный генератор
        target_hours:            целевой SLA в часах
        max_hours:               максимальный SLA в часах
        task_counter:            порядковый номер для external_id
        task_gen_cfg:            секция config['simulation']['task_generation'];
                                 если None — используются значения по умолчанию
        cito_probability_override: если задан — переопределяет cito_probability из конфига
                                   (используется для сценария «Всплеск CITO»)
    """
    cfg = task_gen_cfg or {}

    weights = cfg.get("modality_weights", _DEFAULT_MODALITY_WEIGHTS)
    mod_names, mod_probs = _build_modality_tables(weights)
    modality = rng.choices(mod_names, weights=mod_probs, k=1)[0]

    if cito_probability_override is not None:
        cito_prob = cito_probability_override
    else:
        cito_prob = cfg.get("cito_probability", _DEFAULT_CITO_PROBABILITY)
    is_cito = (modality == "ECG_REST") and (rng.random() < cito_prob)
    urgency_class = "CITO" if is_cito else "план"

    complexity_base = cfg.get("complexity_base", _DEFAULT_COMPLEXITY_BASE)
    spread = cfg.get("complexity_spread", _DEFAULT_COMPLEXITY_SPREAD)
    base_s = complexity_base.get(modality, 1.0)
    complexity = round(base_s * rng.uniform(1.0 - spread, 1.0 + spread), 2)

    t_arr = sim_time_min
    deadline_target = t_arr + target_hours * 60.0
    deadline_max = t_arr + max_hours * 60.0

    task_id = uuid.UUID(int=rng.getrandbits(128), version=4)
    return SimTask(
        id=task_id,
        external_id=f"sim-{task_counter:06d}",
        modality=modality,
        urgency_class=urgency_class,
        complexity=complexity,
        arrived_at=t_arr,
        deadline_target=deadline_target,
        deadline_max=deadline_max,
    )


def generate_doctor_pool(
    config: dict,
    rng: random.Random,
    num_doctors_override: Optional[int] = None,
) -> list[SimDoctor]:
    """
    Динамически генерирует пул врачей для симуляции из секции doctor_pool в config.
    Используется только если sim_doctors не задан или передан num_doctors_override.
    """
    pool_cfg = config.get("doctor_pool", {})
    n = num_doctors_override if num_doctors_override is not None else pool_cfg.get("size", 9)
    base_mu: float = pool_cfg.get("base_productivity", 17.0)
    variation: float = pool_cfg.get("productivity_variation", 0.15)

    default_probs = {
        "ECG_REST": 0.95,
        "HOLTER":   0.55,
        "SMAD":     0.40,
        "ECHO_KG":  0.25,
        "EEG":      0.20,
        "ENMG":     0.10,
    }
    spec_probs: dict = pool_cfg.get("specialization_probs", default_probs)
    ordered_specs = sorted(spec_probs.keys())

    doctors: list[SimDoctor] = []
    for i in range(n):
        specs = [m for m in ordered_specs if rng.random() < spec_probs[m]]
        if not specs:
            fallback = max(spec_probs, key=lambda m: spec_probs[m])
            specs = [fallback]

        factor = 1.0 + rng.uniform(-variation, variation)
        mu_q = round(max(base_mu * 0.5, base_mu * factor), 2)

        doctors.append(SimDoctor(
            id=f"doc_{i + 1:03d}",
            specializations=specs,
            productivity_rate=mu_q,
        ))
    return doctors


def make_doctors_from_config(
    config: dict,
    rng: Optional[random.Random] = None,
    mode: str = "evaluation",
    allow_synthetic: bool = False,
) -> tuple[list[SimDoctor], str]:
    """Создаёт пул SimDoctor из config.yaml и возвращает источник данных."""
    sim_docs_cfg = config.get("sim_doctors", [])
    docs_cfg = config.get("doctors", [])

    if mode == "operational" and docs_cfg:
        return [
            SimDoctor(
                id=f"sim-{d['id']}",
                specializations=d["specializations"],
                productivity_rate=d.get("productivity_rate", 6.0),
            )
            for d in docs_cfg
        ], "doctors"

    if sim_docs_cfg:
        return [
            SimDoctor(
                id=d["id"],
                specializations=d["specializations"],
                productivity_rate=d.get("productivity_rate", 6.0),
            )
            for d in sim_docs_cfg
        ], "sim_doctors"

    if docs_cfg:
        return [
            SimDoctor(
                id=f"sim-{d['id']}",
                specializations=d["specializations"],
                productivity_rate=d.get("productivity_rate", 6.0),
            )
            for d in docs_cfg
        ], "doctors"

    if "doctor_pool" in config and rng is not None:
        if mode == "operational" and not allow_synthetic:
            raise RuntimeError(
                "Operational mode requires explicit 'doctors:'. "
                "Pass --allow-synthetic to override for theoretical scenarios."
            )
        return generate_doctor_pool(config, rng), "synthetic_pool"

    raise ValueError("No doctor source found in config")


def arrival_process(
    env,
    lambda_per_min: float,
    rng: random.Random,
    sla_params: dict,
    task_gen_cfg: Optional[dict] = None,
    hourly_profile: Optional[list] = None,
    day_duration_min: float = 480.0,
):
    """SimPy-генератор нестационарного пуассоновского потока методом thinning.

    Метод разрежения (Lewis & Shedler, 1979):
    1. Генерируем события с МАКСИМАЛЬНОЙ интенсивностью λ_max.
    2. Принимаем событие с вероятностью p(t) = c(h) / max(c).
       c(h) — коэффициент hourly_profile для текущего часа смены h.

    hourly_profile: список 8 коэффициентов для каждого часа 8-часовой смены.
    Если None — используется стационарный режим (c=[1.0]*8).

    lambda_per_min — СРЕДНЯЯ интенсивность потока за смену.
    """
    profile = hourly_profile or [1.0] * 8
    # Нормируем профиль к среднему 1.0, чтобы средняя интенсивность
    # за смену оставалась равной lambda_per_min.
    mean_profile = sum(profile) / len(profile) if profile else 1.0
    norm_profile = [p / mean_profile for p in profile] if mean_profile > 0 else [1.0] * 8
    lambda_max_per_min = lambda_per_min * max(norm_profile)

    counter = 0
    while True:
        interval = rng.expovariate(lambda_max_per_min)
        yield env.timeout(interval)
        now = env.now

        # Определяем текущий час в 8-часовой смене (повторяется каждый день)
        minute_in_day = now % day_duration_min
        hour_in_day = int(minute_in_day // 60)
        hour_idx = min(hour_in_day, len(profile) - 1)
        scale = norm_profile[hour_idx]
        accept_prob = scale / max(norm_profile)

        # Отбор события (thinning)
        if rng.random() >= accept_prob:
            continue

        task = generate_task(
            sim_time_min=now,
            rng=rng,
            target_hours=sla_params.get("target_hours", 2.0),
            max_hours=sla_params.get("max_hours", 24.0),
            task_counter=counter,
            task_gen_cfg=task_gen_cfg,
        )
        counter += 1
        env.task_buffer.append(task)
        # Уведомляем диспетчер о новом задании (event-driven dispatch)
        if hasattr(env, 'new_work') and not env.new_work.triggered:
            env.new_work.succeed()
