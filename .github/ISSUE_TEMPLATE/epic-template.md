---
name: "Epic Issue"
description: "Major decision record + initiative. Create tasks as sub-issues — not in this body."
title: "Epic: [ID] Brief Title"
labels: ["epic", "ai-architect"]
assignees: ''
---

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

Only constraints that override the in-repo guardrails set (`docs/guardrails/`). Cite stable **Guardrail IDs** (e.g. `CPP-TEST-003`) — do not restate full gate text.

### Deviations

<!--
Do not write deviation values here. Record each one in docs/guardrail-deviations.yml with
`epic:` set to this epic's ID; issues-sync.py renders them into the Guardrails section below.
Field definitions: https://github.com/pirlruc/guardrails#deviation-rule
-->

<!-- List the Guardrail IDs this epic authorizes a deviation for, or delete this section. -->


## References

<!-- Guardrail IDs, related epics, legacy source_adr IDs, methodology tag — not task verification commands -->
<!-- Example: CPP-TEST-003, CPP-DOC-001 — https://github.com/pirlruc/guardrails -->
<!-- Methodology: https://github.com/pirlruc/methodologies/tree/1.5.0/github-issue-adr -->

## Epic Acceptance Criteria

- [ ] End-to-end scenario:

<!-- Keep acceptance at epic level. Per-file steps belong in task sub-issues only. -->

## AI metadata

- **creator:** AI_Architect_1
- **confidence_score:**
