"""
Пакетный запуск экспериментов главы 5 (whatimwaitingfor.md).
Запуск из каталога tms:  python scripts/run_ch5_experiments.py

Пишет results/ch5/<batch>/aggregated.jsonl и run_manifest.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {sec}s"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{sec}s"


def run_batch(
    name: str,
    args: list[str],
    batch_index: int,
    batch_total: int,
    started_at: float,
) -> dict:
    out_dir = ROOT / "results" / "ch5" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_jsonl = out_dir / "aggregated.jsonl"
    if out_jsonl.exists():
        out_jsonl.unlink()

    cmd = [PY, "-m", "simulation.runner", "--output", str(out_jsonl), *args]
    t0 = time.perf_counter()
    elapsed_before = t0 - started_at
    print(
        f"\n=== [{batch_index}/{batch_total}] START {name} ===",
        flush=True,
    )
    print(
        "Command:",
        " ".join(str(part) for part in cmd),
        flush=True,
    )
    print(
        f"Elapsed total before batch: {_format_duration(elapsed_before)}",
        flush=True,
    )
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
    }
    r = subprocess.run(cmd, cwd=str(ROOT), env=env)
    elapsed = time.perf_counter() - t0
    elapsed_total = time.perf_counter() - started_at
    rec = {
        "name": name,
        "batch_index": batch_index,
        "batch_total": batch_total,
        "exit_code": r.returncode,
        "elapsed_sec": round(elapsed, 2),
        "elapsed_total_sec": round(elapsed_total, 2),
        "cmd": cmd,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = out_dir / "run_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    if r.returncode != 0:
        print(
            f"=== [{batch_index}/{batch_total}] FAIL {name} "
            f"code={r.returncode} after {_format_duration(elapsed)} ===",
            file=sys.stderr,
            flush=True,
        )
    else:
        print(
            f"=== [{batch_index}/{batch_total}] OK {name} "
            f"in {_format_duration(elapsed)} -> {out_jsonl} ===",
            flush=True,
        )
    return rec


def main() -> int:
    os.chdir(ROOT)
    batches = [
        (
            "p1_validation",
            [
                "--scenario",
                "validation",
                "--seed",
                "0",
                "--algo",
                "all",
            ],
        ),
        (
            "p2_mmc_fifo",
            [
                "--scenario",
                "mmc-validation",
                "--algo",
                "FIFO",
                "--days",
                "30",
                "--n-runs",
                "30",
                "--seed",
                "42",
            ],
        ),
        (
            "p2_baseline_wll",
            [
                "--scenario",
                "baseline",
                "--algo",
                "all",
                "--days",
                "30",
                "--n-runs",
                "30",
                "--seed",
                "42",
                "--assignment-strategy",
                "wll",
            ],
        ),
        (
            "p2_baseline_edf_round_robin",
            [
                "--scenario",
                "baseline",
                "--algo",
                "EDF",
                "--days",
                "30",
                "--n-runs",
                "30",
                "--seed",
                "42",
                "--assignment-strategy",
                "round-robin",
            ],
        ),
        (
            "p3_cito_burst",
            [
                "--scenario",
                "cito-burst",
                "--algo",
                "all",
                "--days",
                "1",
                "--n-runs",
                "100",
                "--seed",
                "42",
            ],
        ),
        (
            "p4_growth20",
            [
                "--scenario",
                "growth20",
                "--algo",
                "all",
                "--days",
                "30",
                "--n-runs",
                "30",
                "--seed",
                "42",
            ],
        ),
        (
            "edge_doctor_outage",
            [
                "--scenario",
                "doctor-outage",
                "--algo",
                "all",
                "--days",
                "30",
                "--n-runs",
                "30",
                "--seed",
                "42",
                "--doctor-outage",
                "doc_001",
                "--outage-start",
                "60",
                "--outage-duration",
                "60",
            ],
        ),
    ]

    started_at = time.perf_counter()
    total_batches = len(batches)
    print(
        f"Starting chapter 5 batch run: {total_batches} batches",
        flush=True,
    )
    summary = []
    for idx, (name, extra) in enumerate(batches, start=1):
        rec = run_batch(name, extra, idx, total_batches, started_at)
        summary.append(rec)
        elapsed_total = time.perf_counter() - started_at
        avg_batch_sec = elapsed_total / len(summary)
        remaining_batches = total_batches - len(summary)
        eta_sec = avg_batch_sec * remaining_batches
        print(
            f"Progress: {len(summary)}/{total_batches} batches completed | "
            f"elapsed={_format_duration(elapsed_total)} | "
            f"eta~{_format_duration(eta_sec)}",
            flush=True,
        )

    master = {
        "batches": summary,
        "all_ok": all(b["exit_code"] == 0 for b in summary),
        "root": str(ROOT / "results" / "ch5"),
    }
    master_path = ROOT / "results" / "ch5" / "MASTER_MANIFEST.json"
    master_path.parent.mkdir(parents=True, exist_ok=True)
    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)
    print(
        f"MASTER_MANIFEST: {master_path}",
        flush=True,
    )
    print(
        "Finished all batches in "
        f"{_format_duration(time.perf_counter() - started_at)}",
        flush=True,
    )
    return 0 if master["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
