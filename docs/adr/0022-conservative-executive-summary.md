# ADR 0022: Conservative executive summary with withheld market comparison

## Decision

Build a run-level executive summary from the immutable validation result, BASE landed-
cost scenario, every rank-1 evidence-backed offer, and the structured data-gap summary.
Map validation disposition to deterministic decision and recommendation codes:

- `NEEDS_HUMAN_REVIEW` → `HUMAN_REVIEW_REQUIRED` /
  `RESOLVE_ERRORS_BEFORE_PURCHASE`;
- `NEEDS_VERIFICATION` → `VERIFICATION_REQUIRED` /
  `VERIFY_GAPS_BEFORE_PURCHASE`;
- `PASSED` → `COMMERCIAL_REVIEW_REQUIRED` /
  `REVIEW_TERMS_BEFORE_PURCHASE`.

Return no, single, or multiple-leading supplier-candidate status and preserve each
rank-1 candidate across comparison groups, including ties, with its original/normalized
price, score, source, and evidence labels. Always mark
candidate due diligence `UNVERIFIED`.

Keep Iranian market price and potential gross-spread values null and set
`WITHHELD_NO_APPROVED_BENCHMARK` until an approved, comparable benchmark provider and
input contract exist. Use the same pure policy in the tenant-scoped API and newly
generated Persian reports. Never interpret the summary as purchase authorization.

## Consequences

- A Level-1 result UI can consume a compact decision contract without reimplementing
  validation, tie handling, or gap logic.
- The BASE landed-cost amount remains reproducible and traceable to the detailed ledger.
- Missing market evidence is visible through stable null/status fields instead of an
  invented Iranian price or margin.
- Even a `PASSED` validation result still requires commercial review; deterministic data
  quality alone cannot approve terms, supplier identity, compliance, or payment.
