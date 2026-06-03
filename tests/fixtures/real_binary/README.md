# Real-binary integration fixtures

This directory holds opt-in real-world document fixtures used by the
`graphtor_integration`-marked round-trip suite in
`tests/test_graphtor_real_binary_integration.py`.

## Why this is opt-in

The docline → graphtor-docs ingestion contract is exercised end-to-end in
`tests/test_graphtor_ingestion_contract.py` against synthetic inputs. Real
binaries add coverage that the readers can extract structured Markdown from
documents produced by real authoring tools (Word, web exporters, PDF
generators), but they cannot be redistributed in this repository.

To keep CI deterministic and the working tree small, the real-binary suite
**skips automatically** when these fixtures are absent.

## How to enable the suite locally

Drop the following small, redistributable-by-you samples into this directory:

| File | Purpose |
| --- | --- |
| `sample.pdf` | Any small (≤ 1 MB) text-based PDF you have rights to. |
| `sample.docx` | Any small (≤ 1 MB) DOCX with at least one H1, one H2, and one paragraph. |

Then run only the opt-in suite:

```pwsh
pytest -m graphtor_integration tests/test_graphtor_real_binary_integration.py
```

## What the suite checks

For each present fixture, the round-trip asserts:

* The reader returns non-empty Markdown text.
* `assemble_markdown(...)` wraps that body in a v1 frontmatter block.
* `content_sha256` computed by `compute_content_sha256` is a 64-character
  SHA-256 hex digest over the UTF-8 body bytes.
* `source_path` round-trips through `posixify_path` to a forward-slash form.

The suite does **not** assert anything about the textual content of the
fixtures, so any compatible small sample works.

## What not to commit

Do not commit binary samples to this repository. The directory is intentionally
left empty except for this README; per-developer fixtures stay local.
