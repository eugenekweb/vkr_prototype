"""Тесты tie-break политики симуляции (детерминированная и rng)."""

import pytest

from algorithms.base import AlgorithmConfig
from simulation.generators import SimTask
from simulation.simulator import Simulator


def _make_minimal_cfg(sim_tie_break: str) -> dict:
    return {
        "algorithm": {"type": "EDF", "beta": 0.05, "delta": 1e-6, "epsilon": 1.0, "priority_weights": {"CITO": 1000, "план": 1}},
        "sla": {"target_hours": 2, "max_hours": 24, "warning_threshold": 0.5, "cito_assign_epsilon_sec": 5},
        "simulation": {
            "sim_tie_break": sim_tie_break,
            "task_generation": {
                "modality_weights": {"ECG_REST": 1.0},
                "complexity_base": {"ECG_REST": 1.0},
                "complexity_spread": 0.0,
                "cito_probability": 0.0,
            },
        },
        "sim_doctors": [
            {"id": "doc_b", "specializations": ["ECG_REST"], "productivity_rate": 10.0},
            {"id": "doc_a", "specializations": ["ECG_REST"], "productivity_rate": 10.0},
        ],
    }


@pytest.mark.integration
def test_sim_tie_break_deterministic_mode_uses_id_order():
    cfg = _make_minimal_cfg("deterministic")
    sim = Simulator("EDF", AlgorithmConfig(), seed=42, config=cfg, audit_mode="none", scenario="baseline")
    task = SimTask(
        id=__import__("uuid").uuid4(),
        external_id="t1",
        modality="ECG_REST",
        urgency_class="план",
        complexity=1.0,
        arrived_at=0.0,
        deadline_target=120.0,
        deadline_max=1440.0,
    )
    chosen = sim._find_doctor_wll(task)
    assert chosen is not None
    assert chosen.id == "doc_a"


@pytest.mark.integration
def test_sim_tie_break_rng_mode_is_reproducible_with_seed():
    cfg = _make_minimal_cfg("rng")
    task = SimTask(
        id=__import__("uuid").uuid4(),
        external_id="t1",
        modality="ECG_REST",
        urgency_class="план",
        complexity=1.0,
        arrived_at=0.0,
        deadline_target=120.0,
        deadline_max=1440.0,
    )

    sim1 = Simulator("EDF", AlgorithmConfig(), seed=7, config=cfg, audit_mode="none", scenario="baseline")
    sim2 = Simulator("EDF", AlgorithmConfig(), seed=7, config=cfg, audit_mode="none", scenario="baseline")

    # Первый выбор при одинаковом seed должен совпасть.
    c1 = sim1._find_doctor_wll(task)
    c2 = sim2._find_doctor_wll(task)
    assert c1 is not None and c2 is not None
    assert c1.id == c2.id
