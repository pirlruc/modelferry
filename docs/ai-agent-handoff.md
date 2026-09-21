# Agent handover log (modelferry)

Purpose: Continuity for humans and AI agents working on this repository—what was reviewed, decided,
changed, and what should happen next.

## How to update this file

After any **user-requested** change or substantive **repository action** (new config, dependency,
layout, CI, release prep, etc.), add a new entry at the top of **Log entries** (newest first). Each
entry should include:

1. **Date** (ISO-8601, UTC or local—state which).
2. **Trigger** (short quote or paraphrase of the request).
3. **Actions** (files created/edited/deleted; commands run if relevant).
4. **Outcome** (what works now, what was deferred).
5. **Follow-ups** (optional bullets for the next agent).

Do not log purely informational chat with no repo impact unless the user asks to record it.

Issue methodology:
[github-issue-adr](https://github.com/pirlruc/methodologies/tree/main/github-issue-adr). Epics in
[`docs/issues.yml`](issues.yml) are the decision records. Do not add `docs/adr/`.

## Delivery status

| Item                                             | State                                              |
| ------------------------------------------------ | -------------------------------------------------- |
| Package `model-fetcher` / import `model_fetcher` | Implemented on `cursor/model-fetcher-library-a7b4` |
| GitLab registry + generic package download       | Implemented                                        |
| GitLab Unleash and REST flag resolution          | Implemented                                        |
| Live GitHub epic issues                          | Not opened (CLI is read-only in this environment)  |
| `docs/guardrails` submodule                      | Not pinned (`pirlruc/guardrails` returned 404)     |

## Commands

```shell
uv sync --frozen --extra dev
uv run pytest
uv run ruff check src tests examples
uv run ruff format --check src tests examples
uv run mypy -p model_fetcher -p tests
uv run pylint src tests
uv run bandit -c pyproject.toml -r src -q
uv build
```

## Known pitfalls

- Project paths must stay percent-encoded (`group%2Fapp`). `GitLabHttp` sets `raw_path` so httpx
  does not turn `%2F` into a slash.
- Unleash calls do not require `GITLAB_TOKEN`. Registry downloads do.
- A flag that is enabled but has no `model_name` / `version` payload makes
  `download_from_feature_flag` raise `FeatureFlagError`.
- FastAPI is intentionally not a dependency. Pydantic models the public payloads.

## Suggested next work

- Open the Phase 1 epics from `docs/issues.yml` when issue creation is available.
- Pin `docs/guardrails` once that repository is readable.
- Add a GitHub provider via `register_provider` without changing `ModelFetcher`.

______________________________________________________________________

## Log entries (newest first)

### 2026-09-21 (UTC) — Initial model-fetcher library

**Trigger:** Implement `model-fetcher` (`model_fetcher`) using the github-issue-adr methodology,
pirlruc guardrails, and the GitHub scaffold, with Pydantic and uv, and FastAPI where it fits.

**Actions:** Added the pymjolnir-equivalent Python scaffold (setuptools, uv, CI, pre-commit, issue
templates). Implemented the provider facade, atomic cache, GitLab registry downloader, and GitLab
flag client. Recorded decisions in `docs/issues.yml` instead of ADR markdown. Did not add FastAPI:
the library is a download client, and a web app would be a third responsibility.

**Outcome:** Direct download and feature-flag download return a verified `Path`. GitHub as a
provider is only an extension point. Private guardrails, github-scaffold, and methodologies repos
were not readable (HTTP 404), so templates were taken from the public heimdallcv copies and the
quality gates from public pymjolnir.

**Follow-ups:**

- Create the live epic and task issues from `docs/issues.yml`.
- Pin `docs/guardrails` when access exists.
- Add the GitHub provider in a later epic.
- The pre-commit `double-quote-string-fixer` hook is omitted because it rewrites strings to single
  quotes and then `ruff-format` rewrites them back, so the hook chain cannot pass.

______________________________________________________________________

*Last updated: 2026-09-21 UTC.*
