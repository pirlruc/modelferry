---
name: "Task Issue"
description: "Implementation slice. Link as sub-issue of parent epic (Major) or standalone (Standard)."
title: "Task: [ID-TN] Brief Title"
labels: ["task", "ai-implementer"]
assignees: ''
---

<!-- Link this issue as a sub-issue of its epic in the sidebar (Major changes). -->

## Description

<!-- One paragraph: what to implement. Do not restate the parent epic problem/goal. -->

## Decision reference

<!-- For Major changes: link or quote the parent Epic's Y-statement / decision. Delete for Standard changes. -->

## Context to Read First

- `path/to/relevant/file.ext`
- `docs/guardrails/` — applicable Guardrail IDs: <!-- e.g. CPP-TEST-003, CPP-LINT-001 -->

## Instructions

**Modify/create:**

- `path/to/file.ext`

**Steps:**

1.
2.

## Out of Scope

<!-- What this task does NOT cover (may be another task under the same epic) -->

## Acceptance Criteria

- [ ]
- [ ] Tests added or updated (if applicable)

## Verification

<!-- Commands from guardrails or epic constraints only — do not duplicate epic acceptance criteria -->
<!-- Cite Guardrail IDs whose gates this verification exercises -->

```bash
# e.g. cmake --preset default && ctest --test-dir build/default
```

## AI metadata

<!-- Parent epic: use the native sub-issue link (sidebar). Do not duplicate #number here — it drifts. -->

- **creator:** AI_Implementer_1
- **confidence_score:**
- **target_branch:** `feature-<purpose>`
