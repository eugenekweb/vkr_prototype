"""
Smoke package for chapter 5 experiments.

Run from the tms directory:
    python scripts/run_ch5_smoke.py

Default set:
- P1 validation scenario (quick verification)
- baseline_ch5 smoke
- growth20_ch5 smoke
- cito_burst_ch5 smoke
- strict distinguishability check on baseline_ch5

Each command writes its own results/ch5/smoke/<name>/aggregated.jsonl and a run_manifest.json.
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


def _run_command(name: str, args: list[str], index: int, total: int, started_at: float) -> dict:
    out_dir = ROOT / "results" / "ch5" / "smoke" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_jsonl = out_dir / "aggregated.jsonl"
    if out_jsonl.exists():
        out_jsonl.unlink()

    cmd = [PY, "-m", "simulation.runner", "--output", str(out_jsonl), *args]
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
    }

    print(f"\n=== [{index}/{total}] START {name} ===", flush=True)
    print("Command:", " ".join(str(part) for part in cmd), flush=True)

    t0 = time.perf_counter()
    completed = subprocess.run(cmd, cwd=str(ROOT), env=env)
    elapsed = time.perf_counter() - t0
    elapsed_total = time.perf_counter() - started_at

    record = {
        "name": name,
        "index": index,
        "total": total,
        "exit_code": completed.returncode,
        "elapsed_sec": round(elapsed, 2),
        "elapsed_total_sec": round(elapsed_total, 2),
        "cmd": cmd,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }

    manifest_path = out_dir / "run_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)

    if completed.returncode == 0:
        print(
            f"=== [{index}/{total}] OK {name} in {_format_duration(elapsed)} -> {out_jsonl} ===",
            flush=True,
        )
    else:
        print(
            f"=== [{index}/{total}] FAIL {name} code={completed.returncode} after {_format_duration(elapsed)} ===",
            file=sys.stderr,
            flush=True,
        )

    return record


def main() -> int:
    os.chdir(ROOT)

    batches = [
        (
            "p1_validation",
            [
                "--scenario",
                "validation",
                "--algo",
                "all",
                "--seed",
                "0",
                "--audit",
                "none",
            ],
        ),
        (
            "baseline_smoke",
            [
                "--scenario-preset",
                "baseline_ch5",
                "--algo",
                "all",
                "--days",
                "0.2",
                "--n-runs",
                "1",
                "--audit",
                "none",
            ],
        ),
        (
            "growth_smoke",
            [
                "--scenario-preset",
                "growth20_ch5",
                "--algo",
                "all",
                "--days",
                "0.2",
                "--n-runs",
                "1",
                "--audit",
                "none",
            ],
        ),
        (
            "cito_burst_smoke",
            [
                "--scenario-preset",
                "cito_burst_ch5",
                "--algo",
                "all",
                "--days",
                "0.2",
                "--n-runs",
                "1",
                "--audit",
                "none",
            ],
        ),
        (
            "strict_baseline",
            [
                "--scenario-preset",
                "baseline_ch5",
                "--algo",
                "all",
                "--days",
                "0.2",
                "--n-runs",
                "1",
                "--audit",
                "none",
                "--strict-distinguishability",
            ],
        ),
    ]

    started_at = time.perf_counter()
    total = len(batches)
    print(f"Starting smoke package: {total} commands", flush=True)

    manifest: list[dict] = []
    for index, (name, args) in enumerate(batches, start=1):
        record = _run_command(name, args, index, total, started_at)
        manifest.append(record)
        elapsed_total = time.perf_counter() - started_at
        remaining = total - index
        eta_sec = (elapsed_total / index) * remaining if index else 0.0
        print(
            f"Progress: {index}/{total} commands completed | "
            f"elapsed={_format_duration(elapsed_total)} | eta~{_format_duration(eta_sec)}",
            flush=True,
        )

    master = {
        "commands": manifest,
        "all_ok": all(item["exit_code"] == 0 for item in manifest),
        "root": str(ROOT / "results" / "ch5" / "smoke"),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    master_path = ROOT / "results" / "ch5" / "smoke" / "MASTER_MANIFEST.json"
    master_path.parent.mkdir(parents=True, exist_ok=True)
    with open(master_path, "w", encoding="utf-8") as handle:
        json.dump(master, handle, ensure_ascii=False, indent=2)

    print(f"MASTER_MANIFEST: {master_path}", flush=True)
    print(f"Finished smoke package in {_format_duration(time.perf_counter() - started_at)}", flush=True)
    return 0 if master["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
