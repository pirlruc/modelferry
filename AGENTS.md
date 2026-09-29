<!-- Generated from .cursor/rules by scripts/render-agent-instructions.py. Edit the .mdc files, then re-run that script. -->

# Agent instructions

Cursor applies `.cursor/rules/*.mdc` (`alwaysApply` and `globs`). This file is
that always-on contract for every other agent that reads AGENTS.md
(https://agents.md/). If both are already in context, follow the rules once.
Edit the `.mdc` files and re-run `scripts/render-agent-instructions.py`.

## File-scoped skills

Glob-scoped rules are indexed in [SKILLS.md](SKILLS.md). Each skill's
instructions are in `.agents/skills/<name>/SKILL.md`
(https://agentskills.io/specification). Cursor sets
`disable-model-invocation` because the matching `.mdc` glob already attaches
the same text. Other agents apply a skill when its description matches.

- [python-quality-gates](.agents/skills/python-quality-gates/SKILL.md)
- [container-images](.agents/skills/container-images/SKILL.md)
- [dependency-updates](.agents/skills/dependency-updates/SKILL.md)
- [supply-chain-artifacts](.agents/skills/supply-chain-artifacts/SKILL.md)
- [release-publish](.agents/skills/release-publish/SKILL.md)

## Always-on rules

# Agent workflow guardrails

## Never without explicit approval

| Action | Examples |
|--------|----------|
| Installing on the system OS | `apt-get install`, `brew install`, `pip install` / `pip install --user` into system Python, `npm i -g`, SDK/toolchain installers, `vcpkg install` outside the manifest |
| Writing to git history | `git commit`, `git tag`, `git merge`, `git rebase`, `git cherry-pick`, submodule pointer bumps |
| Creating or moving refs | `git branch`, `git checkout -b`, `git switch -c`, branch deletion (local or remote) |
| Publishing | `git push`, `gh pr create`, `gh pr merge`, `gh release create`, creating issues via `issues-sync.py` |

### No approval needed

Using tools already on PATH; project-local environments (`uv sync`, `pip install` into `.venv`, `npm ci` in the
repo); configuring/building into repo build directories; running tests; pulling/running Docker images.
See [build-test-environments.mdc](.cursor/rules/build-test-environments.mdc).

When a task requires any gated action above, stop and ask, stating exactly what will be run.
Approval is per action, not per session: a prior "yes" to a commit is not a "yes" to push.

## Branch naming

Create branches as `feature-<purpose>`, lowercase, hyphen-separated:

- `feature-odr-concepts`, `feature-protobuf-export`, `feature-agent-rules`
- not `feat/odr`, `nuno/fix`, `patch-1`

## Related

- Commit message format: [conventional-commits.mdc](.cursor/rules/conventional-commits.mdc)
- Handoff hygiene: [ai-agent-handoff.mdc](.cursor/rules/ai-agent-handoff.mdc)
- Build/test environments (local, venv, then Docker): [build-test-environments.mdc](.cursor/rules/build-test-environments.mdc)
- Guardrail compliance before finishing: [guardrails-compliance.mdc](.cursor/rules/guardrails-compliance.mdc)
- Issue and decision methodology: [github-issue-adr.mdc](.cursor/rules/github-issue-adr.mdc)
- Referencing other repos: [cross-repo-links.mdc](.cursor/rules/cross-repo-links.mdc)

---

# Conventional Commits

When the user asks for a commit (or you commit with explicit approval), use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

## Format rules

- **Subject:** imperative mood, lowercase, no trailing period, ~72 chars max
- **Scope:** optional but recommended — module, library folder, or area (e.g. `traits`, `drawer`, `ci`, `docs`)
- **Body:** explain *why*, not *what*; wrap at ~72 chars
- **Breaking changes:** `feat!:` or footer `BREAKING CHANGE: <description>`

## Allowed types

| Type | Use for |
|------|---------|
| `feat` | New capability or user-visible behavior |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `chore` | Maintenance, tooling, deps (no production code behavior change) |
| `refactor` | Code change without fixing a bug or adding a feature |
| `test` | Tests only |
| `ci` | CI/CD workflow or pipeline changes |
| `build` | Build system, CMake, Gradle, vcpkg |
| `perf` | Performance improvement |
| `style` | Formatting, whitespace (no logic change) |

## Examples

```
feat(traits): add is_detected_v concept alias

fix(ci): restore blocking flag on cpp-docs workflow

docs(issues): document github-scaffold sync in issues-index

chore(scaffold): sync epic template Y-statement section

refactor(drawer): simplify page element layout validation

test(flow): cover typed graph cycle detection
```

## Scope guardrails

Approval for commits, pushes, and OS installs lives in
[agent-workflow.mdc](.cursor/rules/agent-workflow.mdc). Do not amend, force-push, or skip
hooks unless the user requests it. Match the consuming repo's existing commit
message style when in doubt.

## Related

- Approval gates and branch naming: [agent-workflow.mdc](.cursor/rules/agent-workflow.mdc)
- Issue methodology: [github-issue-adr.mdc](.cursor/rules/github-issue-adr.mdc)
- Handoff hygiene: [ai-agent-handoff.mdc](.cursor/rules/ai-agent-handoff.mdc)

---

# AI agent handoff maintenance

`docs/ai-agent-handoff.md` is the living handoff doc for the next agent. Treat it as part of session hygiene.

## At session start

When the task involves repo work (not pure Q&A), read `docs/ai-agent-handoff.md` before making changes.

## At session end

Before finishing, update `docs/ai-agent-handoff.md` if **any** of the following changed during the session:

- Delivery phase status, reconciliation, or GitHub issue/milestone state
- Verification commands, CI workflows, or quality gates
- Toolchain pins, key paths, or module architecture
- New pitfalls, workarounds, or agent conventions discovered
- Suggested next work priorities

Skip updates for read-only questions with no repo impact.

## What to update (keep concise)

| Section | Update when |
|---------|-------------|
| Delivery status table | Phase/epic marked done or reconciliation completed |
| Commands / CI | New or changed build, test, or deploy commands |
| Known pitfalls | New failure mode and fix |
| Suggested next work | Priorities shift after completed work |
| Recent history | Notable commits or branch context worth remembering |

Do **not** duplicate full content from `docs/issues.yml` or `README.md` — link to them and keep only the snapshot an agent needs in the first two minutes.

## Related docs

When handoff status changes, also update `docs/issues.yml` when closing or reconciling phases.

When guardrails are referenced, use [`docs/guardrails/`](https://github.com/pirlruc/guardrails) in the consuming repository — see [guardrails-compliance.mdc](.cursor/rules/guardrails-compliance.mdc).

Issue methodology: [github-issue-adr.mdc](.cursor/rules/github-issue-adr.mdc) (Epic = decision record; applies to **new issues only**).

When recording commits in **Recent history**, use [Conventional Commits](https://www.conventionalcommits.org/) — see [conventional-commits.mdc](.cursor/rules/conventional-commits.mdc).

Record host-only gaps that cannot use a project-local env or Docker under known pitfalls — see [build-test-environments.mdc](.cursor/rules/build-test-environments.mdc).

Refresh the footer line: `*Last updated: …*`.

---

# Build and test environments

Use what is already available locally before reaching for a container. Docker remains the path when a
tool is missing from the host and cannot be satisfied by a project-local environment.

## Order of preference

1. Tools already on the host PATH — no install.
2. Project-local environments that do not touch the system OS — e.g. `.venv` / `uv sync`, project
   `node_modules` / `npm ci`, CMake or Gradle builds into repo build directories.
3. Docker, the repo `.devcontainer/`, or a repo container runner when the tool is not available via (1)
   or (2).
4. Host-only cases that cannot be containerized (device or emulator tests, host-native valgrind,
   platform SDKs). Document a new gap in `docs/ai-agent-handoff.md` under known pitfalls.

## What needs no approval

- Running tools already on PATH
- Creating or using project-local envs (`uv sync`, `pip install` into `.venv`, `npm ci` in the repo)
- Configuring and building into repo build directories
- Running tests
- Pulling and running Docker images

## What needs approval

Installing into the **system OS** — see [agent-workflow.mdc](.cursor/rules/agent-workflow.mdc). Needing a missing
tool is the signal to use a project-local env or to containerize, not to install system-wide.

## Keeping host and container builds apart

Use a distinct build directory per execution context so CMake and Gradle caches never mix absolute paths:

```bash
build/            # container
build-host/       # host-native
```

## Reference implementation

[heimdall](https://github.com/pirlruc/heimdall) runs host PATH plus project-local virtualenvs first and fills the
remaining gaps in Docker via
[`scripts/check-ci-docker.sh`](https://github.com/pirlruc/heimdall/blob/main/scripts/check-ci-docker.sh), with a
per-tool host-vs-Docker resolution table. Mirror that structure when adding container runners to a repo.

## Related

- Approval gates for system installs: [agent-workflow.mdc](.cursor/rules/agent-workflow.mdc)
- Recording host-only gaps: [ai-agent-handoff.mdc](.cursor/rules/ai-agent-handoff.mdc)

---

# Cross-repo linkage

Every repository is standalone. Where a sibling repo happens to sit on disk is incidental to the machine it was
cloned on, so nothing committed may depend on it.

## Use

```markdown
https://github.com/pirlruc/<repo>
https://github.com/pirlruc/<repo>/tree/<ref>/<path>
https://github.com/pirlruc/<repo>/blob/<ref>/<path>
```

Pin `<ref>` to a tag or SHA when the link backs a decision, a threshold, or a pinned submodule. Use `main` only for
links that should always track the tip.

## Do not use

| Anti-pattern | Why |
|--------------|-----|
| `../../guardrails/cpp/guardrails.md` | Assumes a shared parent directory |
| `/home/<user>/Developer/...` | Machine-specific absolute path |
| `documentation/guardrails/...` from another repo | Assumes a monorepo that does not exist |
| A library folder name as a path root (`traits/docs/issues.yml`) | Assumes the old monorepo layout |

## Scope

Applies to markdown, `.mdc` rules, scripts, CI workflows, and `.gitmodules` URLs.

Relative paths remain correct **within** a repo — `docs/issues.yml`, `.github/scaffold/scripts/sync-templates.sh` —
including into a submodule checkout, because the submodule is part of that repo's tree.

## Consuming another repo's content

Pin it as a submodule with an HTTPS URL and reference it through the local mount point:

```bash
git submodule add https://github.com/pirlruc/guardrails.git docs/guardrails
```

Scripts that need the consuming repo root derive it from `git rev-parse --show-toplevel` or an explicit
`CONSUMING_REPO_ROOT`, never from a hardcoded folder list.

## Related

- Approval gates for submodule pointer bumps: [agent-workflow.mdc](.cursor/rules/agent-workflow.mdc)
- Guardrails submodule pinning: [guardrails-compliance.mdc](.cursor/rules/guardrails-compliance.mdc)

---

# Guardrails compliance

Each repo pins [pirlruc/guardrails](https://github.com/pirlruc/guardrails) at `docs/guardrails/`. That submodule is
the org default, not a suggestion. Before finishing repo work, confirm the repo still complies with it.

## Check

1. The submodule is initialized and pinned (`git submodule status docs/guardrails` shows a SHA, not `-`).
2. Gates the change touches match `docs/guardrails/<lang>/profile.thresholds.yml`.
3. Behaviour the change touches matches the principles in `docs/guardrails/<lang>/guardrails.md`.
4. Every existing entry in `docs/guardrail-deviations.yml` is still needed and past-due `review:` dates are raised.

## When the repo does not comply

Never silently lower a gate, loosen a CI condition, or add a suppression to make a check pass. Choose one of three
paths and say which you are taking:

| Situation | Action |
|-----------|--------|
| The repo is wrong | Fix the repo to meet the guardrail |
| The guardrail is wrong for everyone | Propose the change to [pirlruc/guardrails](https://github.com/pirlruc/guardrails) with an explanation and **ask for approval**. If rejected, fall back to one of the other two rows |
| The guardrail is right but this repo genuinely cannot meet it | Record a deviation |

Stricter than the org default is always allowed and needs no record.

## Recording a deviation

One entry in the repo's `docs/guardrail-deviations.yml`, and nowhere else. Numeric fields are omitted when the
guardrail is not parameterized by a number:

```yaml
deviations:
  - id: CPP-TEST-003
    key: statement_coverage
    org_default: 95
    repo_value: 90
    why: Legacy module lacks fixture coverage; remediating in Phase 2
    epic: COV-001
    owner: <maintainer>
    approved_by: Engineering Lead
    review: 2026-12-31
```

Lowering a gate below the org default requires an Epic acting as the decision record and Engineering Lead approval.
`issues-sync.py` renders these entries into the Epic body — do not also paste them into `docs/issues.yml` or into the
issue text by hand.

Field definitions: [guardrails deviation rule](https://github.com/pirlruc/guardrails#deviation-rule).
Process and approval flow:
[guardrail-compliance.md](https://github.com/pirlruc/methodologies/blob/1.6.0/github-issue-adr/docs/process/guardrail-compliance.md).

## Related

- Approval gates: [agent-workflow.mdc](.cursor/rules/agent-workflow.mdc)
- Epic as decision record: [github-issue-adr.mdc](.cursor/rules/github-issue-adr.mdc)

---

# github-issue-adr methodology

[github-issue-adr](https://github.com/pirlruc/methodologies/tree/1.6.0/github-issue-adr) is the methodology for every
repo carrying this scaffold. Do not introduce a second decision-record format alongside it.

## Core model

| Concept | Where it lives |
|---------|----------------|
| Decision record | An **Epic** issue — not an ADR markdown file |
| Unit of work | A **Task** issue, linked as a native sub-issue of its Epic |
| Decision log | The GitHub issue list, filtered by the `epic` label |
| Authored backlog | `docs/issues.yml` in the repo |

Applies to **new** issues only. Existing issues are not retroactively reformatted.

## Rules

- New Epic issues include a **Decision (Y-statement)**: `In the context of <use case>, facing <concern>, we decided <option>, to achieve <benefit>, accepting <trade-off>.` Standard Tasks do not. Do not rewrite an existing issue only to add one.
- Do not create `docs/adr/` or `decisions/` markdown trees. If a decision needs recording, it is an Epic.
- Do not maintain task checklists in the Epic body — they drift from the sub-issues. Use native sub-issue linking.
- Title IDs are stable and cited everywhere: `Epic: [TOOL-001] …`, `Task: [TOOL-001-T1] …`.
- Cite Guardrail IDs (e.g. `CPP-TEST-003`) in Epic constraints, Task verification, and PR descriptions.
- Every PR references its Task, and its Epic when the change is Major.

## docs/issues.yml is the source of truth

Author issues in `docs/issues.yml`, then sync. Never hardcode issue content into scripts, and never hand-create an
issue that the manifest should own — the two drift immediately.

```bash
python3 .github/scaffold/scripts/issues-sync.py --repo pirlruc/<repo> --yaml docs/issues.yml --dry-run
```

Creating issues is a publishing action and needs approval — see [agent-workflow.mdc](.cursor/rules/agent-workflow.mdc). Run
`--dry-run` first and show the result.

Schema: [`docs/issues-schema.md`](https://github.com/pirlruc/github-scaffold/blob/main/docs/issues-schema.md).

## Related

- Guardrail compliance and deviations: [guardrails-compliance.mdc](.cursor/rules/guardrails-compliance.mdc)
- Approval gates: [agent-workflow.mdc](.cursor/rules/agent-workflow.mdc)
- Handoff hygiene: [ai-agent-handoff.mdc](.cursor/rules/ai-agent-handoff.mdc)

---

# Continuous-improvement prompt maintenance

Applies only when `docs/continuous-improvement.md` exists in this
repo. Inert elsewhere. That file is the prompt pasted into the repository's GitHub Agents → Automations
configuration for the **ai-reviewer** cloud-agent run.

## When to update

Refresh the prompt in the same session if any of the following change:

| Trigger | Example |
|---------|---------|
| Surface the prompt reviews | Scripts, templates, Cursor rules, agent instructions, language packs, process docs, reusable workflows, CI toolchain Dockerfiles |
| Pin or schema drift | Methodology/guardrails pin bump; `docs/issues-schema.md`; label vocabulary |
| Automation contract | Output shape, tool allowlist, or trigger assumptions |

Skip updates for read-only questions with no impact on those surfaces.

## Anti-staleness (load-bearing)

The prompt **must not** carry a file-by-file inventory, version pin, Guardrail ID count, or commit SHA that
duplicates the repo. Name **surfaces** (what each area is for); tell the agent to derive filenames, pin
values, and counts from the checkout at run time. Baked-in trees and numbered path inventories are how
the previous prompts rotted.

## Required section skeleton

Keep these sections, in order, across every repo that carries the file:

1. **Role** — reviewer identity and least-friction goal
2. **Automation context** — single-repo scope; cite companions by URL only; no sibling checkouts
3. **Task** — ordered steps; start with inventory + idempotency; end with PR or no-op.
   The Task (or an early review step it calls) **must** instruct the agent to identify
   **improvements, bugs, and design flaws** in this repository's current code, scripts,
   templates, and docs — not only process/docs hygiene. That review scope belongs in the
   **prompt**, not in this Cursor rule.
4. **Output contract** — `docs/issues.yml` entries via PR; never create issues directly
5. **Surfaces** — short role table, not a file tree
6. **Non-negotiable constraints** — flag removals as **requires user decision**
7. **Automation configuration** — suggested trigger, required tools, no secrets in the prompt

## Output contract

- Propose new work as entries appended to `docs/issues.yml` in a pull request.
- Never `gh issue create` (or equivalent) from the automation — that bypasses the authored-manifest
  contract and the publishing approval gate.
- The `ai-reviewer` label is applied by `issues-sync.py` after a human merges and syncs; provenance in
  the prompt uses epic id prefixes (`GS-`, `GR-`, `MTH-`, …) and the PR description.
- Schema: [`docs/issues-schema.md`](https://github.com/pirlruc/github-scaffold/blob/main/docs/issues-schema.md).

## Related

- Issue methodology: [github-issue-adr](https://github.com/pirlruc/github-scaffold/blob/main/.cursor/rules/github-issue-adr.mdc)
- Approval gates: [agent-workflow](https://github.com/pirlruc/github-scaffold/blob/main/.cursor/rules/agent-workflow.mdc)
- Handoff hygiene: [ai-agent-handoff](https://github.com/pirlruc/github-scaffold/blob/main/.cursor/rules/ai-agent-handoff.mdc)

---
