---
title: "Workspace-Specific Policy Proposal Template Reference"
description: "Reference copy of the dynamic policy proposal template instantiated into .autoharness/policy-proposals/ by tune-harness Step 2.4"
---

When `tune-harness` Step 1.8.5 detects policy-gap candidates in `docs/compound/`, Step 2.4 instantiates `.autoharness/policy-proposals/{suggested_policy_id}.md` using `{autoharness_home}/templates/policies/policy-proposal.md.tmpl`:

```markdown
---
policy_id: "{{POLICY_ID}}"
policy_type: "workspace-specific"
status: "proposed"
proposed_at: "{{PROPOSED_AT}}"
evidence_count: {{EVIDENCE_COUNT}}
---

# {{POLICY_TITLE}}

## Status: Proposed

This policy was auto-proposed by `auto-tune` based on recurring patterns in the compound
learning library. Review and decide: accept (copy to `.github/policies/` or append to
`workflow-policies.md`) or reject (delete this file with a note in the tuning report).

## Policy Definition

| Field | Value |
|---|---|
| **APPLIES_TO** | {{APPLIES_TO}} |
| **GATE_POINT** | {{GATE_POINT}} |
| **PRECONDITION** | {{PRECONDITION}} |
| **POSTCONDITION** | {{POSTCONDITION}} |
| **VIOLATION_ACTION** | {{VIOLATION_ACTION}} |

## Rationale

{{POLICY_RATIONALE}}

## Evidence

Derived from {{EVIDENCE_COUNT}} compound learnings sharing the pattern `{{PATTERN_KEY}}`.

Evidence references:

{{EVIDENCE_REFS}}
```
