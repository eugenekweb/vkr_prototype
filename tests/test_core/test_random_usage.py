"""Регрессионная проверка: запрет global random.* в коде симуляции."""

from __future__ import annotations

import ast
from pathlib import Path

# Проверяем только контур симуляции/статистики, где критична воспроизводимость.
TARGET_FILES = [
    Path("simulation/simulator.py"),
    Path("simulation/generators.py"),
    Path("simulation/stats.py"),
    Path("simulation/runner.py"),
]

# Разрешаем только создание local RNG через random.Random(...).
ALLOWED_RANDOM_ATTRS = {"Random"}


def _find_forbidden_random_calls(file_path: Path) -> list[tuple[int, str]]:
    src = file_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    violations: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            # random.<attr>(...)
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "random":
                attr = node.func.attr
                if attr not in ALLOWED_RANDOM_ATTRS:
                    violations.append((node.lineno, attr))
    return violations


def test_no_forbidden_global_random_calls_in_simulation_modules():
    all_violations: list[str] = []
    for rel in TARGET_FILES:
        path = Path(__file__).resolve().parents[2] / rel
        violations = _find_forbidden_random_calls(path)
        for lineno, attr in violations:
            all_violations.append(f"{rel}:{lineno} uses random.{attr}(...) ")

    assert not all_violations, "\n".join(all_violations)
