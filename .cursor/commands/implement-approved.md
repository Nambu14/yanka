---
name: "Implement approved step"
description: "Implement only the step approved in the immediately preceding plan"
category: Workflow
tags: [yanka, implement, workflow, implementation]
---

Follow **incremental-workflow** and **yanka-project**.

## Preconditions

- The **last assistant message** must be a plan that ended with “Reply `approve <step-id>`”.
- I must have explicitly approved in this chat, e.g. `approve 5.1` or `go on 5.1`.
- If approval is missing or ambiguous → **stop** and ask; do not guess.

## Your job this turn

1. Implement **only** the approved step ID (or `$ARGUMENTS` if I named the step there).
2. Run verification from that plan.
3. Post the **completion report** (summary, changes table, verify results, pass criteria checkboxes).
4. Mark `IMPLEMENTATION.md` ✓ **only after** tests pass.
5. Name the logical **next** step — **do not implement it** without a new plan.

## Hard stops — do NOT

- Bundle the next step
- Re-plan and implement in one turn unless I explicitly approved multiple steps (e.g. `approve 5.1+5.2`)
