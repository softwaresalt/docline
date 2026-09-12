# Ship session memory — HashiCorp MDX normalization preprocessor

- **Session:** ship-hashicorp-mdx-normalizer-2026-09-11
- **Date:** 2026-09-11
- **Agent:** ship
- **Branch:** feat/github-markdown-extension
- **Shipment:** 062-S (still `active` — not yet shipped; shipment close is a Step 6
  post-merge operation, deliberately not performed in this session)
- **Feature:** 071-F (`done`)
- **Tasks:** 071.001-T .. 071.011-T (all `done`, archived under `.backlogit/archive/`)
- **Phase:** Steps 1-4 complete, quality gates green, backlog closed for tasks/feature;
  Step 5 (PR lifecycle) next.

## What was built

A temporary, disposable Python preprocessor (test-first, red->green throughout):

- `scripts/_hashicorp_mdx/selection.py` — product classification (19 versioned + 4
  unversioned, live-corrected from the plan's assumed 20/4) + latest-version selection,
  faithfully ported from the external repo's `gather-version-metadata.mjs`.
- `scripts/_hashicorp_mdx/normalize.py` — MDX->MD transform pipeline: frontmatter
  preserve, fenced-code protect/restore, placeholder protect/restore
  (`<TYPE>`/`<PATH>`/`<VALUE>`/`<NAMESPACE>`, incl. hyphenated forms), callout/Tabs/
  CodeTabs/CodeBlockConfig/VideoEmbed transforms, unhandled-construct tally.
- `scripts/hashicorp_mdx_normalize.py` — CLI orchestrator: containment-guarded writes
  (`ContainmentViolation`/`guard_write_path`, always bounded to `--dest`), streaming
  `process_corpus()` shared identically between dry-run and `--execute`, JSON report,
  dry-run-by-default with `--execute` required to write.
- `docs/design-docs/2026-09-11-hashicorp-mdx-normalization-requirements-evidence.md` —
  E.T1 deliverable: selection findings, construct-transform table, three real bugs found
  and fixed via full-corpus dry-run testing, unhandled-construct inventory, exact
  operator `--execute` command (documented, never run), nine numbered requirements for a
  future first-class docline MDX capability.

## Containment discipline (honored throughout, verified)

- Nothing was ever created/modified/deleted outside `C:\Source\GitHub\docline`.
- `C:\Source\Docs\tf-unified-dev-docs-normalized` (the real external destination) was
  **never written**. Every dry-run/test invocation used a `tmp_path`-derived or
  synthetic-fixture destination.
- All test runs used a repo-local pytest basetemp (`build\.pytest-tmp`) — no OS-temp
  files created outside the repo.
- The exact operator `--execute` command is documented in the script's `--help` epilog
  and in the requirements-evidence doc §7. It was never executed by this agent.

## Real-corpus validation (ran 3 times across bug fixes, always zero writes)

Final findings (matches pre-implementation grounding, with two live-verified
corrections vs. the plan/deliberation — see requirements-evidence doc §3.1):

- 23 products total (19 versioned + 4 unversioned); `global` excluded (shared partials).
- vault->v2.x, terraform->v1.16.x, terraform-policy->v0.2.x (beta),
  terraform-enterprise->2.0.x (correction vs. plan's assumed v202507-1 — real corpus has
  newer semver-style directories the plan's investigation missed).
- Totals: 5,566 `.mdx` normalized, 59 `.md` copied, 2,139 assets copied, 1,259 partials
  skipped, 164 other skipped.
- Unhandled-construct tally after 3 bug fixes: 89 distinct tags, 472 occurrences (down
  from 102 distinct before fixes).

Three real bugs found and fixed via full-corpus dry-run testing (all regression-tested):
1. Unhandled-construct tag scan could span newlines to an unrelated `>` (false-positive
   tallies like `EOF`/`YOUR`/`GITHUB`). Fixed: bounded scan to a single line.
2. Placeholder-protect regex didn't cover hyphenated placeholders (`<YOUR-ORG>`). Fixed:
   extended char class to `[A-Z0-9_-]*`.
3. Fence-boundary regex had no indentation awareness; real corpus routinely indents
   fenced code under numbered-list continuations. Fixed: capture leading indent, require
   closing fence to match via backreference.

Known residual limitation (documented, not fixed): space-separated placeholders like
`<YOUR USER>` are not masked by the current placeholder regex (by design — extending to
allow spaces risks masking real prose). Noted in the requirements-evidence doc.

## Quality gates (all green on final committed state)

- `uv run ruff check .` — all checks passed (6 findings from new files fixed: 3 auto-fixed
  via `--fix`, 3 line-length issues fixed manually).
- `uv run ruff format --check .` — 301 files formatted (3 new files reformatted, 298
  pre-existing files unaffected).
- `uv run pytest --basetemp=build\.pytest-tmp` (full repo suite) — **2179 passed, 6
  skipped**, no regressions. New suite alone: 58 passed (25 selection + 25 normalize + 8
  CLI/dry-run, including the real-corpus integration test).

## Commits (all on `feat/github-markdown-extension`, no merge yet)

- `fd626ac` feat(scripts): HashiCorp product/version selection for MDX normalization
- `ff5dbf3` feat(scripts): HashiCorp MDX->MD normalization transform pipeline
- `c119c44` feat(scripts): HashiCorp MDX normalize CLI orchestrator + dry-run tests
- `673c7bb` docs(design): HashiCorp MDX normalization requirements-evidence writeup
- `5b571cc` chore(backlog): complete 071-F tasks and feature under shipment 062-S

## Next steps

1. Step 5 PR lifecycle: local review gate, full quality-gate re-run, PR body with
   Local Review Readiness block, push branch, present to operator.
2. **Wait for explicit operator approval before any merge** — hard requirement, no
   auto-merge.
3. Step 6 post-merge closure (shipment 062-S close, `operational-closure`,
   `compact-context`, knowledge graduation) only after merge is independently confirmed.
4. Cite the exact `--execute` operator command in the PR body; never run it.
