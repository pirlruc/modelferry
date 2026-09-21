______________________________________________________________________

## name: "Epic Issue" description: "Major decision record + initiative. Create tasks as sub-issues — not in this body." title: "Epic: [ID] Brief Title" labels: ["epic", "ai-architect"] assignees: ''

<!-- Set Milestone in the issue sidebar (not in this body). -->

<!-- This Epic IS the decision record — no ADR markdown file. See pirlruc/methodologies github-issue-adr pack. -->

## Overview

**Problem:**

**Goal:**

## Decision (Y-statement)

<!-- Optional one-liner for Major decisions. Delete this section if not needed. -->

<!-- Format: In the context of <use case>, facing <concern>, we decided <option>, to achieve <benefit>, accepting <trade-off>. -->

## Out of Scope

<!-- List what this epic deliberately excludes. Do not duplicate task-level file lists here. -->

## Architecture & Context

- **Target architecture:**
- **Modules impacted:**
- **Dependencies:** <!-- Link to other epics/issues, not task details -->

## Epic-Specific Constraints

Only constraints that override the in-repo quality gates. Cite stable **Guardrail IDs** when
`docs/guardrails/` is pinned — do not restate full gate text.

### Deviation (when lowering a gate)

<!-- Duplicate this block per deviation. Delete if none. -->

- **Guardrail ID:**
- **Org default:**
- **Epic value:**
- **Why:**

## References

<!-- Guardrail IDs, related epics, methodology tag — not task verification commands -->

<!-- Methodology: https://github.com/pirlruc/methodologies/tree/1.0.0/github-issue-adr -->

## Epic Acceptance Criteria

- [ ] End-to-end scenario:

<!-- Keep acceptance at epic level. Per-file steps belong in task sub-issues only. -->

## AI metadata

- **creator:** AI_Architect_1
- **confidence_score:**
