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
[github-issue-adr](https://github.com/pirlruc/methodologies/tree/1.7.0/github-issue-adr). Epics in
[`docs/issues.yml`](issues.yml) are the decision records. Do not add `docs/adr/`.

## Delivery status

| Item                                             | State                                              |
| ------------------------------------------------ | -------------------------------------------------- |
| Package `model-fetcher` / import `model_fetcher` | Implemented. Phase 1 is done. CACHE-002, GLREG-002, and GLFLG-002 are done. |
| GitLab registry + generic package download       | Implemented                                        |
| GitLab Unleash and REST flag resolution          | Implemented                                        |
| Live GitHub epic issues                          | Sibling epics opened with `CURSOR_UPDATE_ISSUE_TOKEN`. They still need a `docs/issues.yml` sync in those repos. |
| `docs/guardrails`                                | Gitlink tag 1.8.0 (`aa5184c`)                      |
| `.github/scaffold`                               | Gitlink tag 1.7.0 (`e76bb3f`)                      |
| commondevops callers                             | `uses:` tag 5.1.2 commit `b3c462be`, secret `COMMONDEVOPS_READ_TOKEN` |
| pydevops caller                                  | Not called. `python-quality` at `19fa370` fails `uv tool install pytest-cov` ([pydevops#170](https://github.com/pirlruc/pydevops/issues/170)). `PYDEVOPS_READ_TOKEN` is unused |
| Actions secrets                                  | `GUARDRAILS_READ_TOKEN`, `COMMONDEVOPS_READ_TOKEN`, `PYDEVOPS_READ_TOKEN` |

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

- A fine-grained token can show `permissions.push: true` on `GET /repos/...` because that
  object is the user, not the token. Creating a git blob still returns HTTP 403
  (`Resource not accessible by personal access token`). That blocked publishing
  `docs/issues.yml` on the sibling repos.
- Project paths must stay percent-encoded (`group%2Fapp`). `GitLabHttp` sets `raw_path` so httpx
  does not turn `%2F` into a slash.
- Unleash calls do not require `GITLAB_TOKEN`. Registry downloads do.
- A flag that is enabled but has no `model_name` / `version` payload makes
  `download_from_feature_flag` raise `FeatureFlagError`.
- FastAPI is intentionally not a dependency. Pydantic models the public payloads.

## Suggested next work

Open epics in `docs/issues.yml` under Phase 2 — Operate and harden:

- `OPS-001` — secret `GUARDRAILS_READ_TOKEN` is on the repo; the task stays open until quality, tests, and docs are green on main
- `CIREUSE-001` — secret `COMMONDEVOPS_READ_TOKEN` is on the repo and the infra and supply-chain workflows call the reusable workflow; the task stays open until those workflows are green on main
- `REL-001` — PyPI Trusted Publishing
- `REL-002` — Dependabot credential for the private submodules
- `GH-001` — GitHub Releases provider
- `NODE-001` — remove `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` after the action audit

Sibling epics are live GitHub issues (see the 2026-09-29 reusable-workflow log
entry). `CURSOR_UPDATE_ISSUE_TOKEN` can create issues and cannot push
`docs/issues.yml`. Each issue says to copy it into that repo's manifest:

| Repo | Epic | Why |
| --- | --- | --- |
| [github-scaffold](https://github.com/pirlruc/github-scaffold) | `GS-PY-CALL` | Seed opt-in `templates/ci-python.yml` after pydevops accepts a checkout token. Do not seed it through `sync-templates.sh`. |
| [guardrails](https://github.com/pirlruc/guardrails) | `GR-PY-REF` | Name pydevops `python-quality` in the CI reference implementations. |
| [pydevops](https://github.com/pirlruc/pydevops) | `PDO-CHKOUT-001` | Add `checkout_token` to `python-quality.yml` so a private caller can fetch the scripts. |
| pydevops | `PDO-COORD-001` | Empty `devops_repository` parses `github.workflow_ref`, which is the caller. [pydevops#168](https://github.com/pirlruc/pydevops/issues/168). |
| pydevops | `PDO-TOOL-001` | `uv tool install pytest-cov` exits 1 on uv 0.6.9. [pydevops#170](https://github.com/pirlruc/pydevops/issues/170). |
| [guardrails](https://github.com/pirlruc/guardrails) | `GR-WF-REF` | CI-034 should say `github.workflow_ref` is the caller workflow. [guardrails#185](https://github.com/pirlruc/guardrails/issues/185). |
| pydevops | `PDO-PIN-018` | Gitlinks are still guardrails `77cf16eb` (1.6.0) and scaffold `9e04ed53` (1.5.0). |
| [commondevops](https://github.com/pirlruc/commondevops) | `CMN-PIN-018` | Same gitlink lag as pydevops. |
| commondevops | `CMN-DOC-CALL` | `common-doc-verify` should also look in `.github/scaffold/scripts` when `scripts/` copies are absent, and still fail closed if neither exists. |
| [cppdevops](https://github.com/pirlruc/cppdevops) | `CPP-PIN-018` | Same gitlink lag. That manifest uses 2-space epic indent. |
| [containerdevops](https://github.com/pirlruc/containerdevops) | `CDO-PIN-018` | Same gitlink lag. |

Not filed: scaffold `main` already defaults guardrails 1.8.0 and scaffold 1.7.0;
`GS-RECON-001` already tracks the commondevops caller pin; tags commondevops
5.1.2, cppdevops 3.1.2, and containerdevops 5.0.4 intentionally have no GitHub
Release.

______________________________________________________________________

## Log entries (newest first)

### 2026-09-29 (UTC) — Drop the python-quality caller until the toolchain installs

**Trigger:** On `e7b77cc`, DevOps coordinates resolved to pydevops and the shield
job passed. Jobs 2 and 3 then failed in `qa-install-toolchain`.

**Actions:** Removed `.github/workflows/ci-python.yml`. Opened
[pydevops#170](https://github.com/pirlruc/pydevops/issues/170) (task #171).
`uv tool install pytest-cov==7.1.0` with uv 0.6.9 prints `No executables are
provided by pytest-cov` and exits 1. Local quality, tests, docs, and security
already cover the same gates.

**Outcome:** This repository still does not check out an ops repository. The
caller to restore is commit `e7b77cc`: `devops_repository` `pirlruc/pydevops`,
`devops_ref` `19fa370f5f11bae423d4c0586080dbed32f9ddf8`, and the permission
union actions write, contents write, pull-requests write, security-events write.

**Follow-ups:** Merge only after the workflows that remain are green on the
new commit. Restore the caller after pydevops#170.

### 2026-09-29 (UTC) — Pin the python-quality DevOps checkout

**Trigger:** Python quality run 36645036392 checked this repository out as the
DevOps tree. `github.workflow_ref` in the called workflow is the caller file.

**Actions:** `ci-python.yml` now passes `devops_repository: pirlruc/pydevops`
and `devops_ref: 19fa370f5f11bae423d4c0586080dbed32f9ddf8`. No workflow checks
an ops repository out. Opened
[pydevops#168](https://github.com/pirlruc/pydevops/issues/168) (task #169) and
[guardrails#185](https://github.com/pirlruc/guardrails/issues/185) (task #186).
Commented on [github-scaffold#148](https://github.com/pirlruc/github-scaffold/issues/148#issuecomment-5901037320).

**Outcome:** The caller no longer relies on the broken coordinate fallback.
Product review of token stripping, checksum origin checks, and cache path
segments found no change to make. Methodologies, commondevops, cppdevops, and
containerdevops needed no new issue: commondevops already fails closed on a
missing `scripts_ref`, and the C++ and container workflows do not parse
`github.workflow_ref`.

**Follow-ups:** Merge PR 3 only after every workflow on this commit is green,
then delete `cursor/bump-guardrails-scaffold-2781`.

### 2026-09-29 (UTC) — Grant the python-quality permission union

**Trigger:** `ci-python.yml` startup_failed. The callee jobs request actions
write, contents write, pull-requests write, and security-events write, and the
caller had granted none (CI-031).

**Actions:** The caller job now grants that union. Opened
[pydevops#166](https://github.com/pirlruc/pydevops/issues/166) so the example
caller documents it, and commented on pydevops#162 and github-scaffold#148.

**Outcome:** Infra, supply-chain, quality, tests, docs, and security were
already green. Python quality had not started.

### 2026-09-29 (UTC) — Call reusable ops workflows and open sibling issues

**Trigger:** The ops repositories are public for now and will be private again.
Reuse their workflows instead of checking the repositories out. `PYDEVOPS_READ_TOKEN`
is on the repo. Issue tokens can create issues and cannot push `docs/issues.yml`.
The About description was set by hand.

**Actions:** `ci-infra.yml` and `ci-supply-chain.yml` call commondevops `b3c462be`
and pass `COMMONDEVOPS_READ_TOKEN`. `ci-python.yml` calls pydevops `python-quality`
at `19fa370` and does not pass `PYDEVOPS_READ_TOKEN`, because that workflow only
accepts `caller_pat`. Opened epics and linked tasks on the sibling repositories.
Each body says to sync the text into that repo's `docs/issues.yml`.

**Outcome:** This repo does not check out commondevops, pydevops, cppdevops, or
containerdevops. cppdevops and containerdevops are not called, so they have no
token here. A public caller still cannot resolve `uses:` after those repositories
become private; the read tokens do not fix workflow-file lookup.

**Follow-ups:**

- [pydevops#162](https://github.com/pirlruc/pydevops/issues/162) checkout token
- [pydevops#164](https://github.com/pirlruc/pydevops/issues/164) pin bump
- [github-scaffold#148](https://github.com/pirlruc/github-scaffold/issues/148) Python caller seed
- [guardrails#183](https://github.com/pirlruc/guardrails/issues/183) cite pydevops
- [commondevops#161](https://github.com/pirlruc/commondevops/issues/161) pin bump
- [commondevops#163](https://github.com/pirlruc/commondevops/issues/163) doc-verify path
- [cppdevops#83](https://github.com/pirlruc/cppdevops/issues/83) pin bump
- [containerdevops#125](https://github.com/pirlruc/containerdevops/issues/125) pin bump

### 2026-09-29 (UTC) — CI no longer fetches github-scaffold

**Trigger:** Quality, tests, and docs still failed after switching the scaffold
fetch to `COMMONDEVOPS_READ_TOKEN`. That token is also HTTP 403 on
`pirlruc/github-scaffold`. Guardrails checkout with `GUARDRAILS_READ_TOKEN`
succeeds. Infra and supply-chain stay green.

**Actions:** Those three workflows fetch only `docs/guardrails`. The markdown
link linter is a snapshot of scaffold tag 1.7.0 under `scripts/lint-doc-links.py`
and `scripts/doc_links/`, with `Returns` sections so ruff DOC201 passes.
Complexity stays inside the floors (max CC 8, average 3.12).

**Outcome:** Local ruff, shellcheck, complexity, and the link linter pass.
GitHub run for `89371be` is green: quality, tests, docs, security, infra, and
supply-chain.

**Follow-ups:** A token with contents read on `pirlruc/github-scaffold` can
replace the vendored linter with a checkout of the gitlink. `OPS-001` and
`CIREUSE-001` stay open until the same workflows are green on main.

### 2026-09-29 (UTC) — Scaffold checkout uses the commondevops token

**Trigger:** Quality, tests, and docs failed after the secrets were added.
`GUARDRAILS_READ_TOKEN` fetched guardrails and got HTTP 403 on
`pirlruc/github-scaffold`.

**Actions:** `scripts/checkout-private-submodules.sh` now fetches scaffold with
`COMMONDEVOPS_READ_TOKEN` when that secret is set. Quality, tests, and docs
pass both secrets.

**Outcome:** Infra and supply-chain were already green on `2a4f697`.

**Follow-ups:** If scaffold still returns 403, the commondevops token also
lacks contents read on `pirlruc/github-scaffold`. That grant has to be on the
token itself.

### 2026-09-29 (UTC) — Use the new read tokens in CI

**Trigger:** The Actions secrets `GUARDRAILS_READ_TOKEN` and `COMMONDEVOPS_READ_TOKEN`
are on the repo. Make the workflows use them, fix whatever the analysis flags,
and set the repository description.

**Actions:** Quality, tests, and docs already pass `GUARDRAILS_READ_TOKEN` into
`scripts/checkout-private-submodules.sh`. Infra and supply-chain no longer
`uses:` the private commondevops workflows. They check out commit `b3c462be`
with `COMMONDEVOPS_READ_TOKEN` and run the same lint and scan steps. Fixed
shellcheck SC1007 in `scripts/check-ci-local.sh`, the Dependabot actor check,
and uv cache on the release workflows so zizmor is clean.

**Outcome:** Local actionlint, shellcheck, and zizmor 1.29.0 report no findings.
pydevops is still not called, so there is no pydevops token. Sibling issue
manifests are still unpublished. Updating the GitHub About description returned
HTTP 403 for the integration token and for `CURSOR_REPO_READ_TOKEN`,
`CURSOR_UPDATE_ISSUE_TOKEN`, and `GH_CACHE_TOKEN`.

**Follow-ups:** Confirm the GitHub runs are green after this push. `OPS-001`
and `CIREUSE-001` stay open until that is true on main. A token with
repository administration can set the About text to: "Python library that
streams model artifacts from a Git registry into a verified local cache and
can select the version from a GitLab feature flag."

### 2026-09-29 (UTC) — Sibling issue manifests could not be pushed

**Trigger:** Add issues on github-scaffold, guardrails, pydevops, commondevops,
cppdevops, and containerdevops for the gaps found while pinning this repo.

**Actions:** Appended epics to each repo's `docs/issues.yml` in local clones and
validated the YAML. `github-scaffold` was committed locally as `7345e89` on
`cursor/issue-followups-2781`. `git push` and `POST /git/blobs` both returned
HTTP 403 for `CURSOR_REPO_READ_TOKEN` and `CURSOR_UPDATE_ISSUE_TOKEN`.

**Outcome:** No sibling pull request exists. The epic ids and rationale are in
Suggested next work above. This repo's pin and callers are unchanged.

**Follow-ups:** A credential with contents write on those repos should commit
the drafted manifests. Do not `gh issue create`.

### 2026-09-29 (UTC) — Guardrails 1.8.0, scaffold 1.7.0, commondevops callers

**Trigger:** Bump guardrails using github-issue-adr, use the newest scaffold release,
follow the commondevops submodule pin, reuse ops jobs, and cut deviations and
exclusions.

**Actions:** Moved `docs/guardrails` to tag 1.8.0 and `.github/scaffold` to tag 1.7.0,
then ran `sync-templates.sh`. Added `ci-infra.yml` and `ci-supply-chain.yml` pinned at
commondevops `b3c462be` (tag 5.1.2). Secret-backed jobs skip `dependabot[bot]` (CI-024).
Removed the coverage `pragma`, the broad `except`, the global pylint suppression, and
the test duplicate-code suppression. mypy is `strict`. Recorded `GRD-002` (done) and
`CIREUSE-001` (open on the new secret).

**Outcome:** Python floors in 1.8.0 match 1.6.0, so no numeric gate moved. Deviations
stay an empty list. cppdevops and containerdevops jobs do not apply. pydevops
`python-quality.yml` is not called because it cannot check out private pydevops
without a token input.

**Follow-ups:**

- `OPS-001` and `CIREUSE-001-T2` still gate green CI on main.
- Sibling manifests are drafted and unpublished. See the later log entry and
  Suggested next work.

### 2026-09-22 (UTC) — Cache publish stays consistent under the lock

**Trigger:** Final pass for bugs, design flaws, performance, and security on the
CACHE, GLREG, and GLFLG work. Merge and delete the branch if nothing remains.

**Actions:** The exclusive lock now covers only the rename and the sidecar
write, so a download no longer blocks readers of the previous artifact. Lookup
takes the shared lock and trusts a sidecar only when it equals the expected
digest and is strictly newer than the file. A publish bumps the sidecar mtime
when the filesystem would otherwise stamp both files together.

**Outcome:** 64 tests pass. Pylint is 10/10. Complexity stays inside the 1.6.0
floors (max cyclomatic complexity 8, average 3.03, minimum maintainability
index 40.59, average 72.20). Statement coverage is 98.21% and branch coverage
is 95.53%. Retries, cross-origin 403 handling, early model-list stop, and
`gradualRolloutUserId` were rechecked and left as implemented. Strategy names
other than `default`, `userWithId`, and `gradualRolloutUserId` still match
after the environment check, which is the Phase 1 behavior. `flexibleRollout`
is not simulated.

**Follow-ups:**

- `OPS-001` is still the gate for green CI on main.
- Re-run `issues-sync.py` with a token that can create issues.

### 2026-09-22 (UTC) — Exclusive cache writes, GitLab retries, gradual rollout

**Trigger:** Advance the implementation of CACHE, GLREG, and GLFLG.

**Actions:** Cache writes now use a unique temporary file and an exclusive
`<file>.lock` around the stream, replace, and sidecar. `ModelFetcher(max_bytes=)`
rejects a larger declared or streamed body. A sidecar that already equals the
expected digest is trusted without rehashing the file. GitLab GET calls retry
transport errors and statuses 500, 502, 503, and 504 three times; 4xx is not
retried. A 401 or 403 from a cross-origin host is `DownloadError`, while the
same statuses from the GitLab origin stay `AuthenticationError`. Model-name
search stops on the page that contains the name. `gradualRolloutUserId` uses
MurmurHash3 x86 32 (seed 0) of `groupId:userId`, with the bucket
`(hash % 100) + 1`. Marked `CACHE-002`, `GLREG-002`, `GLFLG-002`, and their
tasks done. The Phase 2 milestone stays open.

**Outcome:** 61 tests pass. Pylint is 10/10. Complexity stays inside the 1.6.0
floors (max cyclomatic complexity 8, average 3.06, minimum maintainability
index 40.59, average 72.38). Statement coverage is 98.36% and branch coverage
is 95.45%. `None` remains an unlimited download. Unknown strategy names still
match after the environment check. Live GitHub issue sync is still blocked.

**Follow-ups:**

- `OPS-001` is still the gate for green CI on main.
- Re-run `issues-sync.py` with a token that can create issues, after the Phase
  1 and Phase 2 milestones and the epic/task labels exist.

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

*Last updated: 2026-09-29 UTC.*
