"""Тесты для simulation.exporter."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from simulation.exporter import (
    _mean,
    _median,
    _to_float,
    export_aggregated,
    export_raw_replications,
    load_jsonl,
    main,
)


@pytest.mark.unit
@pytest.mark.simulation
def test_mean_empty_and_values():
    assert _mean([]) == 0.0
    assert _mean([1.0, 2.0, 3.0]) == pytest.approx(2.0)


@pytest.mark.unit
@pytest.mark.simulation
def test_median_empty_odd_even():
    assert _median([]) == 0.0
    assert _median([3.0]) == 3.0
    assert _median([1.0, 5.0, 3.0]) == 3.0
    assert _median([1.0, 4.0, 2.0, 8.0]) == pytest.approx(3.0)


@pytest.mark.unit
@pytest.mark.simulation
def test_to_float_handles_invalid_values():
    assert _to_float(None) == 0.0
    assert _to_float("7.5") == 7.5
    assert _to_float(4) == 4.0
    assert _to_float("bad") == 0.0


@pytest.mark.unit
@pytest.mark.simulation
def test_load_jsonl_ignores_blank_lines(tmp_path):
    path = tmp_path / "input.jsonl"
    path.write_text('{"algorithm": "EDF"}\n\n{"algorithm": "FIFO"}\n', encoding="utf-8")

    rows = load_jsonl(str(path))
    assert len(rows) == 2
    assert rows[0]["algorithm"] == "EDF"
    assert rows[1]["algorithm"] == "FIFO"


@pytest.mark.unit
@pytest.mark.simulation
def test_export_raw_replications_writes_header_and_rows(tmp_path):
    out = tmp_path / "raw" / "replications.csv"
    records = [
        {
            "scenario": "baseline",
            "algorithm": "EDF",
            "replication": 1,
            "seed": 42,
            "sla_cito": 1.0,
            "sla_plan_target": 0.9,
            "sla_plan_max": 1.0,
            "tat_median_min": 10.0,
            "tat_p95_min": 12.0,
            "sigma_w2": 0.3,
            "rho_avg": 0.4,
            "rho_normalized": 0.5,
            "throughput_per_hour": 2.0,
            "avg_queue_length": 1.5,
            "max_queue_length": 4,
            "p95_queue_length": 3,
            "completed_tasks": 12,
            "extra": "ignored",
        }
    ]
    export_raw_replications(records, str(out))

    content = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) == 2
    assert content[0].startswith("scenario,algorithm,replication,seed")
    assert "ignored" not in content[1]


@pytest.mark.unit
@pytest.mark.simulation
def test_export_raw_replications_creates_empty_file_with_header(tmp_path):
    out = tmp_path / "raw.csv"
    export_raw_replications([], str(out))
    assert out.exists()
    assert out.read_text(encoding="utf-8").strip() == (
        "scenario,algorithm,replication,seed,sla_cito,sla_plan_target,sla_plan_max,"
        "tat_median_min,tat_p95_min,sigma_w2,rho_avg,rho_normalized,throughput_per_hour,"
        "avg_queue_length,max_queue_length,p95_queue_length,completed_tasks"
    )


@pytest.mark.unit
@pytest.mark.simulation
def test_export_aggregated_groups_and_aggregates(tmp_path):
    out = tmp_path / "agg" / "aggregated.csv"
    records = [
        {
            "scenario": "baseline",
            "algorithm": "EDF",
            "valid_plan_sample": True,
            "valid_cito_sample": True,
            "valid_tat_sample": True,
            "sla_cito": 1.0,
            "sla_plan_target": 0.9,
            "sla_plan_max": 1.0,
            "tat_median_min": 10.0,
            "tat_p95_min": 12.0,
            "sigma_w2": 0.3,
            "rho_avg": 0.4,
            "rho_normalized": 0.5,
            "throughput_per_hour": 2.0,
            "avg_queue_length": 1.5,
            "max_queue_length": 4,
            "p95_queue_length": 3,
            "completed_tasks": 12,
        },
        {
            "scenario": "baseline",
            "algorithm": "EDF",
            "plan_sample_size": 1,
            "cito_sample_size": 1,
            "tat_sample_size": 1,
            "sla_cito": 0.8,
            "sla_plan_target": 0.7,
            "sla_plan_max": 0.9,
            "tat_median_min": 8.0,
            "tat_p95_min": 9.0,
            "sigma_w2": 0.5,
            "rho_avg": 0.6,
            "rho_normalized": 0.7,
            "throughput_per_hour": 1.0,
            "avg_queue_length": 2.5,
            "max_queue_length": 5,
            "p95_queue_length": 4,
            "completed_tasks": 8,
        },
    ]
    export_aggregated(records, str(out))

    content = out.read_text(encoding="utf-8").splitlines()
    assert len(content) == 2
    assert content[0].startswith("scenario,algorithm,n,")
    assert "baseline" in content[1]
    assert "EDF" in content[1]


@pytest.mark.unit
@pytest.mark.simulation
def test_export_aggregated_empty_input_creates_no_file(tmp_path):
    out = tmp_path / "agg.csv"
    export_aggregated([], str(out))
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("scenario,algorithm,n,")


@pytest.mark.unit
@pytest.mark.simulation
def test_export_aggregated_zero_valid_samples(tmp_path):
    out = tmp_path / "agg.csv"
    records = [
        {
            "scenario": "baseline",
            "algorithm": "FIFO",
            "sigma_w2": 1.0,
            "rho_avg": 0.2,
            "throughput_per_hour": 0.0,
            "avg_queue_length": 0.0,
            "max_queue_length": 0.0,
            "p95_queue_length": 0.0,
        }
    ]
    export_aggregated(records, str(out))
    row = out.read_text(encoding="utf-8").splitlines()[1]
    assert "0,0,0" in row or ",0," in row


@pytest.mark.unit
@pytest.mark.simulation
def test_main_exports_csvs(monkeypatch, tmp_path, capsys):
    import simulation.exporter as exporter_mod

    input_path = tmp_path / "input.jsonl"
    input_path.write_text("ignored\n", encoding="utf-8")
    raw_csv = tmp_path / "raw.csv"
    agg_csv = tmp_path / "agg.csv"
    records = [{"scenario": "baseline", "algorithm": "EDF"}]

    monkeypatch.setattr(exporter_mod, "load_jsonl", lambda path: records)
    calls = []
    monkeypatch.setattr(exporter_mod, "export_raw_replications", lambda recs, path: calls.append(("raw", path, recs)))
    monkeypatch.setattr(exporter_mod, "export_aggregated", lambda recs, path: calls.append(("agg", path, recs)))
    monkeypatch.setattr(exporter_mod.argparse.ArgumentParser, "parse_args", lambda self: SimpleNamespace(
        input=str(input_path),
        raw_csv=str(raw_csv),
        agg_csv=str(agg_csv),
    ))

    exporter_mod.main()
    out = capsys.readouterr().out
    assert "Raw replications" in out
    assert "Aggregated table" in out
    assert calls[0][0] == "raw"
    assert calls[1][0] == "agg"


@pytest.mark.unit
@pytest.mark.simulation
def test_load_jsonl_empty_file(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    assert load_jsonl(str(path)) == []
