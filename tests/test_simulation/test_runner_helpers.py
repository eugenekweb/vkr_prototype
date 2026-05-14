"""Тесты helper-функций simulation.runner."""
from __future__ import annotations

from pathlib import Path

import pytest

from simulation.runner import (
    _apply_simulation_mode,
    _ensure_parent,
    _resolve_output_layout,
    _resolve_scenario_preset,
    _slug,
    _warn_if_algorithms_not_distinguishable,
)


@pytest.mark.unit
@pytest.mark.simulation
def test_slug_normalizes_separators():
    assert _slug("A/B c") == "a-b-c"


@pytest.mark.unit
@pytest.mark.simulation
def test_ensure_parent_creates_nested_directory(tmp_path):
    target = tmp_path / "nested" / "file.jsonl"
    _ensure_parent(str(target))
    assert target.parent.exists()


@pytest.mark.unit
@pytest.mark.simulation
def test_resolve_output_layout_default_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    layout = _resolve_output_layout("results/out.jsonl")
    assert Path(layout["summary_path"]).name == "out.jsonl"
    assert Path(layout["summary_dir"]).name == "summary"
    assert Path(layout["audit_dir"]).name == "audit"
    assert Path(layout["plots_dir"]).name == "plots_input"


@pytest.mark.unit
@pytest.mark.simulation
def test_resolve_output_layout_from_summary_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    layout = _resolve_output_layout("results/summary/out.jsonl")
    assert layout["root"].endswith("results")
    assert Path(layout["summary_path"]).as_posix().endswith("results/summary/out.jsonl")


@pytest.mark.unit
@pytest.mark.simulation
def test_apply_simulation_mode_overrides_profile():
    cfg = {
        "simulation": {
            "mode": "evaluation",
            "modes": {
                "operational": {"mode": "operational", "batch_audit_mode": "sample", "days": 3}
            },
        }
    }
    resolved, mode = _apply_simulation_mode(cfg, "operational")
    assert mode == "operational"
    assert resolved["simulation"]["batch_audit_mode"] == "sample"
    assert resolved["simulation"]["days"] == 3


@pytest.mark.unit
@pytest.mark.simulation
def test_resolve_scenario_preset_aliases():
    presets = {"baselineCH5": {"days": 1}, "validation": {"days": 2}}
    name, preset = _resolve_scenario_preset(presets, "baseline_ch5")
    assert name == "baselineCH5"
    assert preset["days"] == 1


@pytest.mark.unit
@pytest.mark.simulation
def test_resolve_scenario_preset_unknown_raises():
    with pytest.raises(ValueError):
        _resolve_scenario_preset({}, "missing")


@pytest.mark.unit
@pytest.mark.simulation
def test_warn_if_algorithms_not_distinguishable_low_spread():
    records = [
        {"algorithm": "EDF", "sla_plan_target": 0.90, "sla_cito": 0.95, "tat_p95_min": 10, "sigma_w2": 1.0},
        {"algorithm": "FIFO", "sla_plan_target": 0.905, "sla_cito": 0.949, "tat_p95_min": 10.1, "sigma_w2": 1.01},
    ]
    warnings = _warn_if_algorithms_not_distinguishable(records, threshold=0.05)
    assert warnings


@pytest.mark.unit
@pytest.mark.simulation
def test_warn_if_algorithms_not_distinguishable_single_algo():
    records = [{"algorithm": "EDF", "sla_plan_target": 0.90}]
    assert _warn_if_algorithms_not_distinguishable(records) == []


@pytest.mark.unit
@pytest.mark.simulation
def test_warn_if_algorithms_not_distinguishable_missing_metrics():
    records = [{"algorithm": "EDF"}, {"algorithm": "FIFO"}]
    warnings = _warn_if_algorithms_not_distinguishable(records)
    assert warnings
