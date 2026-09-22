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
[github-issue-adr](https://github.com/pirlruc/methodologies/tree/1.5.0/github-issue-adr). Epics in
[`docs/issues.yml`](issues.yml) are the decision records. Do not add `docs/adr/`.

## Delivery status

| Item                                             | State                                              |
| ------------------------------------------------ | -------------------------------------------------- |
| Package `model-fetcher` / import `model_fetcher` | Implemented; Phase 1 epics marked done |
| GitLab registry + generic package download       | Implemented                                        |
| GitLab Unleash and REST flag resolution          | Implemented                                        |
| Live GitHub epic issues                          | Not created. The available token gets HTTP 403 on issue creation. The backlog is `docs/issues.yml`. |
| `docs/guardrails`                                | Gitlink tag 1.6.0 (`584b209`)                      |
| `.github/scaffold`                               | Gitlink tag 1.5.0 (`6f33f78`)                      |

## Commands

```shell
uv sync --frozen --extra dev
uv run pytest
sh scripts/check-ci-local.sh
uv run ruff check src tests examples scripts
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

Open epics in `docs/issues.yml` under Phase 2 — Operate and harden:

- `OPS-001` — Actions secret `GUARDRAILS_READ_TOKEN`
- `REL-001` — PyPI Trusted Publishing
- `REL-002` — Dependabot credential for the private submodules
- `GH-001` — GitHub Releases provider
- `CACHE-002` — exclusive cache writes, size cap, sidecar hits
- `GLREG-002` — retries, cross-origin 403, early model-list stop
- `GLFLG-002` — gradual rollout percentages
- `NODE-001` — remove `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` after the action audit

______________________________________________________________________

## Log entries (newest first)

### 2026-09-22 (UTC) — Improvements moved into the issue manifest

**Trigger:** Record the improvements for the current code as issues, migrate
`docs/improvements.md` into that backlog, and delete the improvements file.

**Actions:** Appended Phase 2 epics to `docs/issues.yml`. Deleted
`docs/improvements.md`. The two completed checkboxes (guardrails pin and the
coverage gate) stay done on `GRD-001` and were not reopened. Publishing the
Phase 1 records is the sync step, not a new open epic.

**Outcome:** The open backlog is `OPS-001`, `REL-001`, `REL-002`, `GH-001`,
`CACHE-002`, `GLREG-002`, `GLFLG-002`, and `NODE-001`. `issues-sync.py
--validate-only` accepts the manifest. A live sync was not published: the
available token is forbidden from creating issues (HTTP 403).

**Follow-ups:**

- `OPS-001` is still the gate for green CI on main.
- Re-run `issues-sync.py` with a token that can create issues, after the Phase
  1 and Phase 2 milestones and the epic/task labels exist.

### 2026-09-21 (UTC) — Final review: redirects, pagination, header safety

**Trigger:** Final pass for bugs, design flaws, performance, and security. Merge the pull
request, update the issues, and delete the branch if nothing remains.

**Actions:** Stopped forwarding `PRIVATE-TOKEN`, `JOB-TOKEN`, and Unleash headers on
cross-origin redirects, and ignored `x-checksum-sha256` from those hosts. Pagination now stops
after 20 pages instead of looping when `x-next-page` does not advance, and a non-numeric page
header is a download error. Rejected control characters in header values and credentials embedded
in `base_url`. Removed the `candidate:` version shortcut that skipped registry lookup. The
submodule fetch script sends the read token as an Authorization header instead of putting it in
the remote URL. The PyPI workflow passes the release tag through the environment. Marked the
Phase 1 epics and tasks done in `docs/issues.yml`.

**Outcome:** 53 tests pass. Pylint remains 10/10. Complexity stays within the 1.6.0 floors
(max cyclomatic complexity 8, minimum maintainability index about 41.6). A non-unique cache temp
name remains the accepted CACHE-001 tradeoff. Downloads still have no size cap, because model
artifacts are expected to be large.

**Follow-ups:**

- CI stays red until `GUARDRAILS_READ_TOKEN` can read the private submodules.
- Configure PyPI Trusted Publishing before the first annotated tag.

### 2026-09-21 (UTC) — Guardrails 1.6.0 complexity floors

**Trigger:** How complex is the code, and make it comply with guardrails 1.6.0.

**Actions:** Measured radon on `src/model_fetcher`. Split every block above cyclomatic complexity 8
and moved flag parsing into `flag_eval.py` so the maintainability index stays at or above 40. Pinned
`docs/guardrails` at tag 1.6.0 and `.github/scaffold` at tag 1.5.0. Split CI into quality, tests,
docs, and security workflows that read `profile.thresholds.yml`. Raised statement and branch
coverage above 95 percent. Recorded the decision as epic GRD-001.

**Outcome:** Max cyclomatic complexity is 8 and the average is about 3.1. Minimum maintainability
index is about 42.6 and the average is about 75. No numeric gate was lowered.

**Follow-ups:**

- CI stays red until `GUARDRAILS_READ_TOKEN` can read `pirlruc/guardrails` and
  `pirlruc/github-scaffold`.
- Private submodule bumps need a Dependabot git credential. The registry block stays commented until
  that secret exists.

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
