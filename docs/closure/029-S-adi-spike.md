---
title: 029-S Azure Document Intelligence spike — third pdf_engine peer
date: 2026-06-11
status: shipped
verdict: KEEP-AS-PEER
verdict_date: 2026-06-12
shipment: 029-S
feature: 027-F
tasks:
  - 027.001-T  # T1 [adi] optional extra
  - 027.002-T  # T2 adi_extractor module
  - 027.003-T  # T3 pdf_engine routing + auto policy
  - 027.004-T  # T4 empirical study (operator runs with credentials)
  - 027.005-T  # T5 this closure doc
related_decisions:
  - docs/decisions/2026-06-10-next-pdf-pipeline-shipment-deliberation.md
  - docs/decisions/2026-06-08-extraction-strategy-study.md
consumed_stashes:
  - F10EB5CB  # ADI spike intent
---

## Verdict (2026-06-12, post-empirical study)

**KEEP-AS-PEER.** ADI remains available as an explicit-opt-in third
engine via `--pdf-engine azure_di`, but the `auto` policy has been
revised to **never** select ADI even when credentials are present.

### Why

The empirical comparison study (`scripts/study/adi_comparison.py`)
processed 15 cosmos-PDF sample ranges (551 pages) at a total cost of
$0.83 in **5.6 minutes wall time (5,902 pages/hour)**. ADI's throughput
advantage is genuine and enormous compared to docling's ~9.5 hours for
the same corpus.

However, **ADI loses on every structural fidelity metric** that matters
for downstream graphtor-docs ingestion (graph DB nodes/edges, vector
chunks, LLM context):

| Metric | ADI vs docling | Notes |
|---|---|---|
| Char length | **−70.1% mean** (range −16% to −98%) | ADI returns drastically less text |
| Headings | **−74.2% mean** (range 0% to −99.5%) | ADI flattens heading hierarchy |
| Tables | **−66.7% mean; ADI returned 0 tables on 10 of 15 ranges** | Complete loss of tabular structure |
| Lists | **−86.7% mean; ADI returned 0 lists on 13 of 15 ranges** | Complete loss of list semantics |
| Structural density / 1k chars | **−5.57 mean** (range −1.73 to −18.95) | ADI is orders of magnitude flatter |

The losses are not borderline. On range-3110-3112, ADI returned 18.95
fewer structural elements per 1k chars than docling — equivalent to
losing the entire AST of that range. On 11 of 15 ranges, ADI's
`prebuilt-layout` model returned zero tables where docling correctly
identified table cells. On 13 of 15 ranges, ADI returned zero lists.

This pattern is consistent with ADI's actual product positioning —
it is descended from "Form Recognizer," designed for invoices, receipts,
and structured forms where layout extraction is the goal. Cosmos-class
technical reference PDFs are dense prose-and-code-and-table content
where docling's RT-DETR layout model + structural recovery wins
decisively.

### Auto policy change (effective 2026-06-12)

`_resolve_layout_engine("auto")` now picks docling when installed and
falls back to heuristic when not. ADI requires explicit
`--pdf-engine azure_di`. The credential check (`AdiCredentialError`
fast-fail) and transient-error fallback chain are preserved for the
explicit path.

### When ADI is still the right choice

Keep ADI in the peer set because it remains the right tool for:

1. **Forms, invoices, receipts, structured documents** — ADI's design
   sweet spot, where docling has not been empirically validated.
2. **Speed-critical operator workflows** where ~$0.0015/page cloud cost
   is acceptable and fidelity loss is tolerable (e.g. quick triage of
   a 1,000-page archive to identify which sections need manual review).
3. **Cost-bound multi-tenant deployments** where local docling
   inference cost (GPU/CPU time × engineer-hours) exceeds the
   per-page Azure list price.

### Follow-up stash candidates

- **Re-validate ADI for forms / invoices corpus** (separate study).
  The cosmos result generalizes the negative finding to technical
  reference PDFs only; ADI may still win on the corpus class it was
  designed for.
- **Add a "fidelity vs throughput" decision matrix to the README**
  pointing operators at the right engine for their corpus class.
- **A029E6EB — DocumentIntelligenceClient caching** is now low-priority
  unless the operator runs ADI in production batch mode; deprioritize
  from medium to low.

---

## Outcome

Wired Azure Document Intelligence (ADI) as an opt-in **third
`pdf_engine` peer** alongside the existing `docling` and `heuristic`
engines. ADI is gated behind the optional `[adi]` extra (no impact on
default installs) and an environment-variable credential check.

**Empirical comparison vs docling on the 5 cosmos sample ranges is
PENDING** — the operator runs `scripts/study/adi_comparison.py` with
their Azure credentials when ready (the script costs ~$0.40 at list
price). This closure doc gets a second pass once those findings land.

## Acceptance criteria

| AC | Statement | Status |
|---|---|---|
| AC1 | T1+T2+T3 wire ADI without breaking docling/heuristic | ✅ 28 new tests pass; existing 1,169 still pass |
| AC2 | T4 empirical study on cosmos ranges (within 10% structural density, <5% wall time, 0 failures) | ❌ **ADI loses on every fidelity metric** (mean −5.57 density delta; 100% table loss on 10/15 ranges). Wall-time win is real (~5,900 pp/hr vs docling's ~360 pp/hr) but quality unacceptable for graphtor-docs ingestion. |
| AC3 | T5 closure with cost analysis + recommended auto policy | ✅ this doc (verdict: KEEP-AS-PEER; auto policy revised) |
| AC4 | All four local quality gates pass | ✅ (T4 live test self-skips when env vars absent) |
| AC5 | Spike output DECIDES production rollout, doesn't mandate it | ✅ auto policy now reverts to docling-first; ADI explicit opt-in only |

## What shipped

### T1 — Optional `[adi]` extra

`pyproject.toml` gained an `[adi]` extra pinning
`azure-ai-documentintelligence>=1.0,<2`. The SDK is NOT pulled in by
the default install; existing environments are unaffected.

### T2 — `src/docline/readers/adi.py`

Public API:
- `read_pdf_adi(path, endpoint=None, key=None, model_id="prebuilt-layout") -> str`
- `AdiCredentialError` (raised when endpoint+key not resolvable)

Implementation:
- Lazy SDK import (raises `DependencyUnavailableError` with install hint when `[adi]` absent)
- Credentials from explicit args OR `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` + `AZURE_DOCUMENT_INTELLIGENCE_KEY` env vars
- Uses `model_id="prebuilt-layout"` and `output_content_format="markdown"` (returns ready-to-ingest markdown)
- Per-call telemetry: page count + wall time + projected cost line item logged via `_log.info`
- 12 tests (11 unit, 1 live-integration env-gated)

### T3 — `pdf_engine` routing

- `pdf_engine` literal extended to `Literal["auto", "docling", "azure_di", "heuristic"]`
- `--pdf-engine azure_di` accepted by `docline process`, `docline ingest local-dir`
- MCP manifest enum updated
- `read_pdf_pages` dispatches `azure_di` to `read_pdf_adi`; result wrapped in a 1-element list to match the per-page contract
- `auto` policy: prefer `azure_di` when `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` env var set AND `[adi]` extra installed; else docling; else heuristic
- `auto` path catches ADI failures and falls back to docling/heuristic so a single Azure-side blip doesn't abort the batch
- 13 tests covering the routing matrix

### T4 — `scripts/study/adi_comparison.py`

Empirical-study harness. Reuses the 5 existing cosmos sample ranges
under `.elt/output/cosmos-triage-022/study/dataset/range-NNNN-NNNN/`.
For each range:

1. Slice the source PDF (`.elt/data/cosmosdb/azure-cosmos-db.pdf`) to the
   range's page indices via `pypdf`
2. Send the sliced PDF to ADI through the new `read_pdf_adi`
3. Save the result as `adi.md` alongside the existing `docling.md` and
   `markitdown.md`
4. Compute the same 25 AST metrics as `scripts/study/evaluate_markdown.py`
5. Emit aggregate `adi-findings.json` + `adi-findings.md` in
   `.elt/output/cosmos-triage-022/study/results/`

Flags: `--source-pdf`, `--range`, `--dry-run`, `--results-dir`.
Idempotent — skips ranges whose `adi.md` already exists.

### T5 — this closure doc

Documents the integration shape, current state, recommended `auto`
policy, cost analysis, and where the empirical-findings update will
land.

## Recommended `auto` policy

Already implemented in `_resolve_layout_engine`:

| Condition | Resolved engine |
|---|---|
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` set AND `[adi]` installed | `azure_di` |
| `[pdf]` installed (`docling` available) | `docling` |
| Otherwise | `heuristic` |

This is **opt-in by configuration, not by code change**: setting the
env var on a machine with `[adi]` installed flips the default. The
operator can override with `--pdf-engine docling` or `--pdf-engine
heuristic` per run.

## Cost analysis (list price, 2026-06)

| Workload | Pages | ADI cost @ $0.0015/page | Docling wall time | ADI wall time est. |
|---|---:|---:|---:|---:|
| Cosmos sample (5 ranges) | ~250 | **$0.38** | hours | minutes |
| Full cosmos PDF | ~4,500 | **$6.75** | ~25 h | ~30 min est. |
| Full Power BI corpus *(if used for PDFs)* | varies | — | — | — |

## Production rollout decision

**KEEP-AS-PEER (provisional)** — pending empirical study findings.

Rationale: the integration is conservative by design. ADI is not
auto-preferred unless the operator explicitly sets the env var, which
constitutes an opt-in signal that they've accepted the cost trade-off.
If the empirical study (T4) shows ADI quality within 10% of docling on
the cosmos sample ranges, the recommendation graduates to **ADOPT** —
update the `auto` policy comment to note ADI is the preferred path for
high-fidelity extraction.

## How to complete the empirical study (operator workflow)

1. Install the extra: `pip install -e .[adi]` (or `uv pip install -e
   .[adi]`)
2. Provision ADI credentials in Azure portal (Cognitive Services →
   Document Intelligence resource → Keys and Endpoint)
3. Set env vars in PowerShell:

   ```powershell
   setx AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT "https://<resource>.cognitiveservices.azure.com/"
   setx AZURE_DOCUMENT_INTELLIGENCE_KEY "<primary-or-secondary-key>"
   # restart shell so setx takes effect
   ```

4. Dry-run to see the plan + projected cost:
   `python scripts/study/adi_comparison.py --dry-run`
5. Run for real (~$0.40 of ADI credits):
   `python scripts/study/adi_comparison.py`
6. Inspect findings:
   `.elt/output/cosmos-triage-022/study/results/adi-findings.md`
7. Amend THIS closure doc (status `shipped-pending-empirical-findings`
   → `verified-adopt` or `verified-keep-as-peer` or
   `verified-abandon`) with the actual metrics

## Invariants enforced / preserved

1. **Optional SDK never required at default install**: `import docline`
   works without `[adi]`; ADI extractor lazy-imports the SDK and raises
   `DependencyUnavailableError` with install hint when absent
2. **No credentials in code or tests**: env-var resolution only;
   `AdiCredentialError` for missing values; test fixtures use mocked SDK
3. **Auto policy is opt-in**: setting env var is the operator's signal
   they've accepted the cost trade-off
4. **Failure tolerance**: `auto` path catches ADI transient failures and
   falls back to docling/heuristic so cloud blips don't abort batches
5. **Telemetry for cost visibility**: every ADI call logs `pages` +
   `wall_s` + `projected_cost_usd` at INFO level

## Rollback

Single shipment, single PR. Rollback = revert the merge commit. The
three peer engines are independent; removing `azure_di` from the
literal restores pre-spike behavior. Existing `docling`/`heuristic`
paths are unaffected by this change.

## Follow-up stashes captured (none yet)

Suggested follow-ups depending on empirical findings:

- **If ADOPT**: stash a "cost guardrail" task (warn when projected per-run
  cost exceeds threshold) before bulk usage
- **If ADOPT**: stash a "managed-identity credential resolution" task to
  enable production deployments without storing keys
- **If KEEP-AS-PEER**: stash a "ADI selective routing" task — let the
  triage scorer route only high-complexity pages to ADI while keeping
  docling as the default
- **If ABANDON**: stash a follow-up to address the specific deficiencies
  observed in the empirical study; remove `azure_di` from `auto` policy
  but keep as explicit-opt-in for operator experimentation
