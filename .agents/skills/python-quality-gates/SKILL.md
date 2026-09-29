---
name: python-quality-gates
description: 'Prove PY-* quality gates still hold before finishing Python edits. Use when editing files that match: **/*.py.'
paths: '**/*.py'
disable-model-invocation: true
---

<!-- Generated from .cursor/rules by scripts/render-agent-instructions.py. Edit the .mdc files, then re-run that script. -->

Cursor applies the matching `.cursor/rules` file by glob and does not auto-invoke this skill. Other agents should follow this skill when the description matches.

# Python quality gates (executable companion to guardrails-compliance)

When you add or edit **Python** (`.py`) files, prove the org Python guardrails still hold
before finishing. This rule supplies **commands**; threshold **numbers** and the deviation
procedure live elsewhere — do not bake numbers into this file.

## Where numbers live

Read floors from `docs/guardrails/python/profile.thresholds.yml` in the consuming checkout
(keys such as `statement_coverage`, `branch_coverage`, `doc_coverage`,
`max_cyclomatic_complexity`, `avg_cyclomatic_complexity`, `min_maintainability_index`,
`avg_maintainability_index`). Resolve tools via [build-test-environments.mdc](../../../.cursor/rules/build-test-environments.mdc)
(`uv run …` from a project-local env). Policy and deviations:
[guardrails-compliance.mdc](../../../.cursor/rules/guardrails-compliance.mdc).

## Prefer local CI parity

If the repo has a local parity script (`CI-008`) — e.g. `bash scripts/check-ci-local.sh` —
run that once. It already enforces the floors. Only if no such script exists, run the
per-gate commands below against the packages the repo measures.

## Per-gate fallback (map to Guardrail IDs)

| Check | Typical command | Guardrail |
|-------|-----------------|-----------|
| Format / lint | `uv run ruff check` and `uv run ruff format --check` | PY-QUAL-001, PY-RUN-002 |
| Types | `uv run mypy` (or the repo's type checker) | PY-RUN-002 |
| Complexity / MI | `uv run radon cc -j` / `mi -j` through the repo gate script | PY-CPLX-001, PY-CPLX-002 |
| Statement + branch coverage | `uv run pytest` with `--cov-branch` and fail-under from thresholds | PY-TEST-002 |
| Doc coverage | `uv run interrogate --fail-under` from thresholds | PY-DOC-001 |
| Docstring style | ruff pydocstyle Google + `pydoclint --style=google` | PY-DOC-002 |

Cite the Guardrail ID in the PR when a gate fails or when recording a deviation.

## Design habit (keeps CC and branch coverage affordable)

Prefer Pydantic models with `model_dump(exclude_none=True)` and lookup tables over long
`if` / `elif` ladders on new or edited code.
