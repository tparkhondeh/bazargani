# ADR 0027: Offer-terms coverage without a completeness score

## Decision

Create a pure per-offer coverage projection over retained price observations and their
immutable supplier-ranking rows. Define an ordered recorded-field vocabulary containing
supplier identity, minimum order quantity, product specification, Incoterm code, named
place, and declared version. Return exact declared/missing field names and count beside
rankability and deduplicated ranking unknown factors.

Separately expose payment terms/method, quote validity, lead time, supplier capacity,
certifications, warranty, and inspection terms as fields not captured by the current
schema. Share the projection between a tenant-scoped endpoint and new Persian reports.
Do not calculate a percentage, promote field presence into verification, infer the
value of an uncaptured term, or equate ranking eligibility with procurement readiness.

## Consequences

- Clients can render an honest checklist without reverse-engineering ranking scores.
- The output distinguishes a missing stored value from a capability the data model does
  not yet support.
- New structured commercial terms require an explicit model/migration and must move
  from the uncaptured list into the recorded vocabulary in a versioned change.
- Supplier identity, terms, capacity, and certifications still require dedicated
  evidence and human verification before commercial action.
