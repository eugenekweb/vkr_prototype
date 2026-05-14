"""Тест воспроизводимости экспериментального контура при фиксированном seed."""
import pytest
import yaml
from algorithms.base import AlgorithmConfig
from algorithms.factory import PrioritizerFactory
from simulation.simulator import Simulator

ALGORITHMS = ["FIFO", "PQ", "AGING", "EDF", "HYBRID"]


def _make_config() -> dict:
    return {
        "algorithm": {
            "type": "EDF",
            "beta": 0.05,
            "delta": 1e-6,
            "epsilon": 1.0,
            "priority_weights": {"CITO": 1000, "план": 1},
        },
        "sla": {"target_hours": 2, "max_hours": 24},
        "simulation": {"baseline_arrival_rate": 446},
        "doctors": [
            {"id": "d001", "specializations": ["ECG_REST", "HOLTER", "SMAD"], "productivity_rate": 1.0},
            {"id": "d002", "specializations": ["ECG_REST", "HOLTER"], "productivity_rate": 1.0},
            {"id": "d003", "specializations": ["ECHO_KG", "ECG_REST"], "productivity_rate": 0.9},
            {"id": "d004", "specializations": ["EEG", "ECG_REST"], "productivity_rate": 0.8},
        ],
    }


def run_simulation(algorithm: str, seed: int, days: float = 1) -> object:
    """Запускает один прогон имитации и возвращает результат."""
    import os
    import tempfile
    config = _make_config()
    config["algorithm"]["type"] = algorithm
    params = AlgorithmConfig.from_dict(config["algorithm"])
    # Используем temp-файл, чтобы не зависеть от CWD при тестах
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        tmp_path = f.name
    sim = Simulator(
        algorithm_type=algorithm,
        params=params,
        seed=seed,
        config=config,
        jsonl_path=tmp_path,
    )
    duration_min = days * 8 * 60.0
    return sim.run_with_rate(duration_min, 446)


@pytest.mark.integration
@pytest.mark.parametrize("algo", ALGORITHMS)
def test_deterministic_reproducibility(algo):
    """
    При одинаковом seed алгоритм даёт детерминированно воспроизводимый результат:
    два запуска с seed=42 дают идентичную последовательность назначений.
    """
    r1 = run_simulation(algorithm=algo, seed=42, days=1)
    r2 = run_simulation(algorithm=algo, seed=42, days=1)
    assert r1.assignment_sequence == r2.assignment_sequence, (
        f"Алгоритм {algo}: последовательности назначений не совпадают при seed=42"
    )
    assert r1.sla_plan_target == r2.sla_plan_target
    assert r1.total_tasks == r2.total_tasks


@pytest.mark.integration
def test_different_seeds_differ():
    """
    Разные seed дают различающиеся последовательности.
    Косвенная проверка: seed управляет входным потоком.
    """
    r1 = run_simulation(algorithm="EDF", seed=42, days=3)
    r2 = run_simulation(algorithm="EDF", seed=99, days=3)
    assert r1.assignment_sequence != r2.assignment_sequence, (
        "Разные seed дали одинаковые последовательности — seed не работает"
    )


@pytest.mark.integration
@pytest.mark.parametrize("algo", ALGORITHMS)
def test_same_seed_same_total_tasks(algo):
    """При одном seed одинаковое число поступивших заданий."""
    r1 = run_simulation(algorithm=algo, seed=7, days=1)
    r2 = run_simulation(algorithm=algo, seed=7, days=1)
    assert r1.total_tasks == r2.total_tasks
