#!/usr/bin/env python3
"""Enforce PY-CPLX-001 and PY-CPLX-002 from the pinned guardrails thresholds.

Reads numeric floors from docs/guardrails/python/profile.thresholds.yml.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path
from typing import Any

import yaml

REQUIRED_KEYS = (
    "max_cyclomatic_complexity",
    "avg_cyclomatic_complexity",
    "min_maintainability_index",
    "avg_maintainability_index",
)
PINNED = Path("docs/guardrails/python/profile.thresholds.yml")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse CLI arguments.

    Args:
        argv: Argument vector, or ``None`` to read the process arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--thresholds", type=Path)
    return parser.parse_args(argv)


def load_thresholds(path: Path) -> dict[str, Any]:
    """Load complexity floors from the pinned Python profile.

    Args:
        path: Thresholds YAML.

    Returns:
        The parsed mapping.

    Raises:
        SystemExit: If the file or a required key is missing.
    """
    if not path.is_file():
        raise SystemExit(f"error: missing thresholds file: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise SystemExit(f"error: {path} missing keys: {', '.join(missing)}")

    return data


def python_files(root: Path) -> list[Path]:
    """Return product and script Python files.

    Args:
        root: Repository root.

    Returns:
        Sorted Python files under ``src`` and ``scripts``.

    Raises:
        SystemExit: If neither tree contains Python.
    """
    collected: list[Path] = []
    for relative in ("src", "scripts"):
        base = root / relative
        if base.is_dir():
            collected.extend(path for path in base.rglob("*.py") if path.is_file())

    files = sorted(collected)
    if not files:
        raise SystemExit(f"error: no Python files under {root}/src or {root}/scripts")

    return files


def collect_metrics(files: list[Path]) -> tuple[list[int], dict[Path, float]]:
    """Return per-block cyclomatic complexity and per-file maintainability.

    Args:
        files: Python files to score.

    Returns:
        Complexities and maintainability scores.
    """
    from radon.complexity import cc_visit
    from radon.metrics import mi_visit

    complexities: list[int] = []
    maintainability: dict[Path, float] = {}
    for path in files:
        source = path.read_text(encoding="utf-8")
        complexities.extend(block.complexity for block in cc_visit(source))
        maintainability[path] = float(mi_visit(source, multi=True))

    return complexities, maintainability


def _cc_failures(values: list[int], floors: dict[str, Any]) -> list[str]:
    """Return PY-CPLX-001 failures.

    Args:
        values: Cyclomatic complexity of each block.
        floors: Threshold mapping.

    Returns:
        Failure messages. Empty when the gate holds.
    """
    if not values:
        return ["PY-CPLX-001: no functions or methods to score"]

    maximum = max(values)
    average = statistics.mean(values)
    failures: list[str] = []
    if maximum > floors["max_cyclomatic_complexity"]:
        failures.append(f"PY-CPLX-001: max CC {maximum} > {floors['max_cyclomatic_complexity']}")

    if average > floors["avg_cyclomatic_complexity"]:
        failures.append(
            f"PY-CPLX-001: avg CC {average:.2f} > {floors['avg_cyclomatic_complexity']}",
        )

    return failures


def _mi_failures(scores: dict[Path, float], floors: dict[str, Any]) -> list[str]:
    """Return PY-CPLX-002 failures.

    Args:
        scores: Maintainability index per file.
        floors: Threshold mapping.

    Returns:
        Failure messages. Empty when the gate holds.
    """
    if not scores:
        return ["PY-CPLX-002: no files to score"]

    lowest = min(scores.values())
    average = statistics.mean(scores.values())
    failures: list[str] = []
    if lowest < floors["min_maintainability_index"]:
        worst = min(scores, key=lambda path: scores[path])
        failures.append(
            f"PY-CPLX-002: min MI {lowest:.2f} < {floors['min_maintainability_index']} ({worst})",
        )

    if average < floors["avg_maintainability_index"]:
        failures.append(
            f"PY-CPLX-002: avg MI {average:.2f} < {floors['avg_maintainability_index']}",
        )

    return failures


def main(argv: list[str] | None = None) -> int:
    """Measure ``src`` and ``scripts`` against the pinned Python complexity floors.

    Args:
        argv: Argument vector, or ``None`` to read the process arguments.

    Returns:
        Zero when both gates pass.
    """
    args = parse_args(argv)
    root = args.root.expanduser().resolve()
    floors = load_thresholds(args.thresholds or (root / PINNED))
    try:
        complexities, scores = collect_metrics(python_files(root))
    except ImportError:
        print("error: radon is required (uv sync --extra dev)", file=sys.stderr)
        return 2

    failures = _cc_failures(complexities, floors) + _mi_failures(scores, floors)
    cc_max = max(complexities) if complexities else 0
    cc_avg = statistics.mean(complexities) if complexities else 0.0
    print(f"CC max={cc_max} avg={cc_avg:.2f}")
    print(f"MI min={min(scores.values()):.2f} avg={statistics.mean(scores.values()):.2f}")
    if not failures:
        print("Python complexity gates passed.")
        return 0

    print("ERROR: Python complexity gates failed:", file=sys.stderr)
    for item in failures:
        print(f"  - {item}", file=sys.stderr)

    return 1


if __name__ == "__main__":
    sys.exit(main())
