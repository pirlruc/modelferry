#!/usr/bin/env python3
"""Enforce PY-TEST-002 statement and branch coverage from pinned thresholds."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

PINNED = Path("docs/guardrails/python/profile.thresholds.yml")
REQUIRED = ("statement_coverage", "branch_coverage")


def load_thresholds(path: Path) -> dict[str, Any]:
    """Load coverage floors.

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
    missing = [key for key in REQUIRED if key not in data]
    if missing:
        raise SystemExit(f"error: {path} missing keys: {', '.join(missing)}")

    return data


def run_pytest(root: Path) -> dict[str, Any]:
    """Run the suite and return the coverage JSON totals.

    Args:
        root: Repository root.

    Returns:
        The ``totals`` object from ``coverage.json``.

    Raises:
        SystemExit: If pytest fails.
    """
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=model_fetcher",
            "--cov-branch",
            "--cov-report=json",
            "-q",
        ],
        cwd=root,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)

    payload = json.loads((root / "coverage.json").read_text(encoding="utf-8"))
    return payload["totals"]


def _percent(covered: int, total: int) -> float:
    """Return a percentage, or 100 when there is nothing to cover.

    Args:
        covered: Covered items.
        total: Items that exist.

    Returns:
        The percentage.
    """
    if total == 0:
        return 100.0

    return 100.0 * covered / total


def main() -> int:
    """Compare pytest-cov totals with the pinned floors.

    Returns:
        Zero when both floors hold.
    """
    root = Path(".").resolve()
    floors = load_thresholds(root / PINNED)
    totals = run_pytest(root)
    statements = _percent(totals["covered_lines"], totals["num_statements"])
    branches = _percent(totals["covered_branches"], totals["num_branches"])
    print(f"statements={statements:.2f} branches={branches:.2f}")
    failures: list[str] = []
    if statements < floors["statement_coverage"]:
        failures.append(
            f"PY-TEST-002: statement coverage {statements:.2f} < {floors['statement_coverage']}",
        )

    if branches < floors["branch_coverage"]:
        failures.append(
            f"PY-TEST-002: branch coverage {branches:.2f} < {floors['branch_coverage']}",
        )

    if not failures:
        print("Coverage gates passed.")
        return 0

    print("ERROR: coverage gates failed:", file=sys.stderr)
    for item in failures:
        print(f"  - {item}", file=sys.stderr)

    return 1


if __name__ == "__main__":
    sys.exit(main())
