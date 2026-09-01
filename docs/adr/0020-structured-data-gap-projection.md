# ADR 0020: Structured data gaps from immutable run evidence

## Decision

Expose a tenant-scoped data-gap projection built only from persisted validation issues
and declared `UNKNOWN` notes in the same immutable research run. Preserve every issue's
code, severity, Persian message, subject, and safe details; preserve individual unknown
text rather than reducing it to the single aggregate `DECLARED_UNKNOWNS` warning.

Use a pure application function to order issues deterministically, count errors,
warnings, and declared unknowns separately, and derive one status:

- `GAPS_REQUIRE_HUMAN_REVIEW` when at least one validation error exists;
- `GAPS_REQUIRE_VERIFICATION` when warnings or declared unknowns exist without errors;
- `NO_RECORDED_GAPS` only when both collections are empty.

Use the same summary calculation in the authenticated API and newly generated Persian
reports. Do not expose raw evidence, mutate completed runs, manufacture resolution
claims, or treat `NO_RECORDED_GAPS` as proof of commercial completeness.

## Consequences

- Result UIs can render an actionable gap queue without parsing Markdown or joining two
  endpoints, while retaining the underlying issue and unknown context.
- Validation disposition/confidence remain visible beside the gap status rather than
  being recomputed or silently replaced.
- One aggregate unknown warning and multiple declared unknown statements remain
  intentionally separate counts.
- Provider-attributed failures and retry state require the future resumable acquisition
  model; this projection does not invent provider execution history that is not stored.
