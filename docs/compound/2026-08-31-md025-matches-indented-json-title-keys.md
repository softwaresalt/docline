---
title: "MD025 front_matter_title matches indented title: keys inside JSON schema blocks"
date: 2026-08-31
agent: ship
context: markdown-lint
tags:
  - markdownlint
  - MD025
  - skills
  - false-positive
  - json-schema
trigger:
  - "MD025 fires on a SKILL.md that has exactly one H1"
  - "You are tempted to weaken MD025 to { front_matter_title: '' } repo-wide"
  - "A markdown file embeds a JSON schema containing a title property"
---

## Problem

`.markdownlint.json` had `"MD025": true` (single H1 per document). A skill file with exactly
one H1 still failed MD025. The obvious "fix" — weakening the rule repo-wide to
`{ "front_matter_title": "" }` — silences it everywhere and removes a real guardrail.

## Root cause

MD025's default `front_matter_title` pattern is:

```text
^\s*title\s*[:=]
```

The leading `\s*` means it is **not anchored to column 0**. Any indented `title:` key matches —
including one nested several levels deep inside a JSON schema in the skill's `input.properties`
block. markdownlint then treats that line as a front-matter title, counts it as an implicit H1,
and reports the document's real H1 as a duplicate.

## Resolution

Scope the suppression to the one offending line instead of weakening the rule globally:

```markdown
<!-- markdownlint-disable-next-line MD025 -->
```

with a short comment explaining that the match is an indented JSON `title` property, not a
heading.

To isolate how many errors a config change actually causes, lint the same file set under both
configs and diff the counts. Here: 11 errors under `"MD025": true` vs 10 under the weakened
config — proving exactly **one** attributable error, which turned out to be this false positive.
The other 10 were pre-existing MD041 violations in upstream skill templates, unrelated to the
config change.

## Lesson

Before relaxing a lint rule repo-wide, isolate the true blast radius by counting errors under
both configurations. A single false positive almost never justifies weakening a rule
everywhere — an inline scoped disable keeps the guardrail intact. Also worth knowing: a
repo-wide `**/*.md` markdownlint run takes 10+ minutes here, so always pass an explicit file
list.
