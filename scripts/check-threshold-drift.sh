#!/bin/sh
# Fail when config/*.profile.thresholds.yml is looser than the pinned
# guardrails submodule. Stricter consumer values stay allowed (CI-022).
set -eu

SCRIPT_DIR="$(dirname "$0")"
SCRIPT_DIR="$(cd "${SCRIPT_DIR}" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

python3 - "${ROOT}" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
pairs = [
    ("python", True),
    ("shell", False),
    ("docker", False),
    ("swift", True),
    ("kotlin", True),
]
higher = {
    "statement_coverage",
    "branch_coverage",
    "doc_coverage",
    "min_maintainability_index",
    "avg_maintainability_index",
    "min_image_efficiency_percent",
}
lower = {
    "max_cyclomatic_complexity",
    "avg_cyclomatic_complexity",
    "pr_size_soft_limit_lines",
    "lint_exception_max_days",
    "image_max_size_mb",
    "ci_image_max_size_mb",
    "base_image_max_age_days",
    "max_critical_vulnerabilities",
    "vuln_ignore_max_days",
    "compose_privileged_services_max",
}

def parse(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"missing {path}")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values

def looser(key: str, consumer: str, analog: str, allow_stricter: bool) -> bool:
    if consumer == analog:
        return False
    if not allow_stricter:
        return True
    try:
        c_num = float(consumer)
        a_num = float(analog)
    except ValueError:
        return True
    if key in higher:
        return c_num < a_num
    if key in lower:
        return c_num > a_num
    return True

failed = False
for name, allow_stricter in pairs:
    consumer_path = root / "config" / f"{name}.profile.thresholds.yml"
    analog_path = root / "docs" / "guardrails" / name / "profile.thresholds.yml"
    if not consumer_path.is_file():
        continue
    consumer = parse(consumer_path)
    analog = parse(analog_path)
    for key, analog_value in analog.items():
        consumer_value = consumer.get(key)
        if consumer_value is None:
            print(f"error: {consumer_path} missing {key}", file=sys.stderr)
            failed = True
            continue
        if looser(key, consumer_value, analog_value, allow_stricter):
            print(
                f"error: {name} {key} consumer {consumer_value} is looser than {analog_value}",
                file=sys.stderr,
            )
            failed = True
    print(f"thresholds ok: {name}")

if failed:
    raise SystemExit(1)
PY
