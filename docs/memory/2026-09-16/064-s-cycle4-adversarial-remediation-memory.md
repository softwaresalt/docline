---
type: stage-session-memory
date: 2026-09-16
agent: stage
shipment: 064-S
feature: 073-F
branch: chore/stage-064-s
cycle: 4 (operator-authorized bounded correction/re-review)
---

# Stage cycle-4 — 064-S adversarial-BLOCKED remediation

## Context

Operator ("Make it so") authorized ONE bounded Stage correction/re-review cycle for
shipment 064-S after a fresh report-only adversarial review returned BLOCKED (2 P1, 3 P2,
1 P3). Authoritative operator contract: Docline redacts ONLY structured source-access
credentials; document body content, URL paths, local filesystem paths, include patterns,
branches, globs, IDs, benign query fields, and all ordinary provenance are preserved
byte-for-byte. NO arbitrary content/path secret scanning.

Strict Stage-role scope: modified only `.backlogit/` planning artifacts, `docs/plans/`,
`docs/decisions/`, `docs/memory/`. No src/test/config edits, no shipment claim, no push,
no PR. Seven-item manifest and five-test-to-one-production DAG unchanged.

## Source behavior verified (read-only) to make plan executable

- `sanitize_source` (src/docline/fetch/staging.py) REDACTS `file://` and absolute/UNC/
  Windows-drive local paths to `<local-path-redacted>` (contradicts contract) and uses
  `parse_qsl`+`urlencode` in `_sanitize_url`, normalizing benign query bytes.
- execute.py `_exception_scrub_replacements` composes into the WARNING/error sink ONLY
  url/repo_url, branch, path_glob, manifest id per source kind (ManifestLocalSource → only
  config.id; LocalFileSource not in replacement set). Local path/include are NEVER composed
  into that live sink — the P1 dishonest-claim root.
- Typed path (`source_keys._sanitize_url_field`) delegates to `sanitize_source` first, so it
  INHERITS the string path's query normalization → fixing the string path fixes both.
- Default production path uses the typed sanitizer (`sanitize_source_key`), not the bare
  string fallback (positional test callers only).

## Findings resolved (all in-scope P1 + all P2/P3)

| # | Sev | Fix |
|---|---|---|
| C4-1 | P1 | 073.002-T: compatibility BARE URL ONLY; require change/removal of sanitize_source local-path redaction branches; new ACs 10-12; contradicting `<local-path-redacted>` test assertions flagged for update. |
| C4-2 | P1 | 073.008-T: removed local-path/include from live WE proof; reduced to branch/path_glob/manifest id; relocated local-path/include proof to typed surface (073.001-T). |
| C4-3 | P2 | 073.009-T: added byte-for-byte benign-query ACs/tests (percent spelling %20/%25, `&` separators, blank/valueless params) vs parse_qsl/urlencode. |
| C4-4 | P2 | 073.003-T: added exact 5-layer benign boundary (preserved) + retained over-cap fail-closed; added helper benign-query + local-path preservation ACs. |
| C4-5 | P2 | 064-S: added CURRENT STATE committed-by-Stage clarification; plan/deliberation "uncommitted" wording corrected. |
| C4-6 | P3 | 073.001-T: "current HEAD cdcf718" -> "current HEAD"; plan provenance cdcf718->cb34426. |

## Files changed

- .backlogit/queue/064-S.md, 073.001-T.md, 073.002-T.md, 073.003-T.md, 073.008-T.md, 073.009-T.md
- docs/plans/2026-09-14-elt-staging-credential-redaction-plan.md (Unit A2, BI, CI, matrix WE note,
  verification criteria 3/7/8, provenance block, cycle-3 wording, appended cycle-4 remediation
  section w/ dispositions + inline persona review, markers attempt:5 / remediation-cycle:4)
- docs/decisions/2026-09-14-elt-staging-credential-redaction-deliberation.md (parallel bare-URL,
  WE sink-scope, uncommitted wording)

## Review

Stage plan review, single-agent declared-degradation (no reviewer-subagent dispatch surface;
anchor route openai/gpt-5.6-sol unavailable -> same-model inline). All personas PASS.
Verdict: PASS. No in-scope P0/P1 remains.

## Residual (accepted / out-of-scope)

- H4 raw-source job_id confirmation-oracle (accepted).
- Over-cap benign-looking query NAME fails closed (accepted false-positive by contract).
- Exact-match intentionally-unredacted variants (token_v2, access_token2, ...) (Finding 7).
- Distinct-contract P-021 entries (79BF0AEC, E89DC095, 9D44B6F3, E7878B1B, 95BD0DC7, 709BDB53) --
  out of 064-S scope.

## Next steps

- Committed by Stage on chore/stage-064-s (conventional format + Copilot trailer). No push/PR.
- Ship claims shipment 064-S for execution when handed off.
