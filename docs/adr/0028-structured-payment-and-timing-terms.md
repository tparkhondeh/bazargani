# ADR 0028: Evidence-bound payment and timing terms

## Decision

Add optional `payment_terms`, `payment_method`, timezone-aware `quote_valid_until`, and
positive integer `lead_time_days` fields to each immutable price observation through
migration `20260901_0012`. Existing rows remain null; parsers and domain invariants must
not infer defaults from price, supplier, Incoterm, or narrative evidence.

Expose the exact structured values in evidence-backed price and supplier-offer views,
and move their field names from the offer-coverage schema-gap list into the ordered
recorded vocabulary. Reports encode payment text as untrusted data. A quote whose declared
validity is earlier than the immutable validation `evaluated_at` receives the warning
`QUOTE_VALIDITY_EXPIRED`; equality remains valid at the recorded boundary.

Keep the existing commercial-completeness score weights unchanged. Missing payment and
timing fields become explicit ranking unknown factors, but presence contributes no new
points and does not establish current validity, acceptability, supplier reliability, or
authority to purchase.

## Consequences

- Clients can display evidence-linked payment and timing facts without parsing raw source
  bodies or supplier notes.
- Legacy and partial offers remain representable without invented contract terms.
- Validation and reports are reproducible because expiry uses persisted evaluation time,
  not the current wall clock.
- Supplier capacity, certifications, warranty, and inspection terms remain explicit
  schema gaps requiring separately designed evidence-bound models.
- Production requires the additive migration and normal backup/rollback gates before a
  release can use the new columns.
