---
date: 2026-06-04
shipment: 013-S
category: pydantic-namespace-handling
keywords: [pydantic, frontmatter, namespace, merge, overwrite, model_dump, webfrontmatter, docline]
confidence: high
evidence: src/docline/app.py:_build_markdown_with_frontmatter, tests/elt/test_process_regression.py::test_html_output_uses_per_page_source_url_and_crawl_depth
---

# Pydantic namespace dicts: always merge, never overwrite

## Problem

When extending a Pydantic-modeled YAML frontmatter that already uses a
nested "namespace" dict (e.g. `docline: dict[str, Any] | None`), reaching
in via `payload.model_dump(mode="json")` and assigning
`payload_dict["my_namespace"] = new_dict` **silently destroys any keys
that the Pydantic model auto-routed into that namespace from elsewhere**.

In docline 013-S we discovered this when adding G3b referentiality fields
under the `docline:` namespace. `WebFrontmatter` already routes
`source_url`, `crawl_depth`, `http_status`, `content_type`, `final_url`,
and `fetched_at` into the same `docline:` block via a pydantic validator
that is invisible from the assembler call site. An overwrite of
`payload_dict["docline"]` lost all of those crawl metadata keys for web
sources — caught only by an existing regression test
(`test_html_output_uses_per_page_source_url_and_crawl_depth`).

## Symptom

A specific subset of consumers (those depending on the auto-routed
namespace keys) loses metadata silently. CI tests against those consumers
fail with `assert "source_url" in frontmatter_block` or similar
"missing field" assertions. The fields are present in `base_data` and in
the Pydantic model instance — they only disappear when the namespace dict
is overwritten in `model_dump` output.

## Fix

Merge instead of assign. Read the existing namespace, layer new keys on
top, and write the merged dict back:

```python
payload_dict = payload.model_dump(mode="json")
if my_namespace is not None:
    existing = payload_dict.get("my_namespace")
    merged: dict[str, object] = {}
    if isinstance(existing, dict):
        merged.update(existing)
    merged.update(my_namespace)
    payload_dict["my_namespace"] = merged
```

## Reusable rule

**When extending a Pydantic-modeled nested namespace dict at the
`model_dump` boundary, treat the existing dict as authoritative and
layer new keys on top.** Never assign a fresh dict to the namespace key.
Document the merge semantics in the docstring of the call site so future
"simplification" PRs do not regress the behavior.

## Detection in code review

Look for any line matching `payload_dict["{namespace}"] = ...` or
`base_data["{namespace}"] = ...` in code that flows through a Pydantic
model with auto-routing into that namespace. Each such line is a
potential silent-data-loss bug. The safer pattern is always a merge.

## Related

- 013-S closure: `docs/closure/013-S-referentiality.md`
- 013-S plan-review (which did NOT catch this issue — plan-review focused
  on the new namespace shape but did not audit pre-existing namespace
  usage): `docs/decisions/2026-06-04-G3b-referentiality-plan-review.md`
- Affected file: `src/docline/app.py` `_build_markdown_with_frontmatter`
