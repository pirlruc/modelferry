#!/bin/sh
# Local CI parity for model-fetcher (CI-008).
# Requires docs/guardrails at the pinned gitlink and a uv environment.
set -eu

root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "${root}"

if [ ! -f docs/guardrails/python/profile.thresholds.yml ]; then
  echo "error: init docs/guardrails (git submodule update --init)" >&2
  exit 1
fi

echo "==> ruff"
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts

echo "==> mypy"
uv run mypy -p model_fetcher -p tests

echo "==> pylint"
uv run pylint src tests

echo "==> complexity (PY-CPLX-001, PY-CPLX-002)"
uv run python scripts/check-python-complexity.py

echo "==> coverage (PY-TEST-002)"
uv run python scripts/check-python-coverage.py

doc_coverage="$(
  uv run python -c 'import yaml; from pathlib import Path; data = yaml.safe_load(Path("docs/guardrails/python/profile.thresholds.yml").read_text()); print(data["doc_coverage"])'
)"

echo "==> doc coverage (PY-DOC-001)"
uv run interrogate --fail-under "${doc_coverage}" src/model_fetcher

echo "==> docstring style (PY-DOC-002)"
uv run pydoclint src/model_fetcher

echo "==> bandit (PY-SEC-002)"
uv run bandit -c pyproject.toml -r src -q

echo "==> pip-audit (PY-SEC-004)"
uv run pip-audit

if [ -f .github/scaffold/scripts/lint-doc-links.py ]; then
  echo "==> markdown links (DOC-LINT-001)"
  uv run python .github/scaffold/scripts/lint-doc-links.py --root "${root}"
fi

echo "Local CI parity passed."
