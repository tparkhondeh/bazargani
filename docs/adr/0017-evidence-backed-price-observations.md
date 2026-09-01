# ADR 0017: Evidence-backed price-observation projection

## Decision

Expose an authenticated, tenant-scoped run endpoint that joins each persisted price
observation to its product-match result, supplier-ranking normalization, evidence, and
source. Return original amount/currency, quoted quantity/unit/MOQ/Incoterm, product
variant/attributes, market layer, source metadata, evidence class/confidence,
transformation, match class/score, comparison group, and normalized amount/currency.

Treat normalized price as a derived comparison value calculated with the BASE scenario
FX path. Preserve the original observation unchanged and return null normalization when
conversion was not possible. Omit raw evidence bodies.

## Consequences

- Price-distribution and comparison clients do not need to join several run endpoints.
- Original and normalized values remain visually and semantically distinct.
- Match and provenance context travel with every price, reducing unsupported product
  comparisons.
- Inner joins make incomplete/corrupt result sets unavailable as apparently complete
  observations; completed result persistence remains atomic.
- This projection does not itself claim a price is an Iranian market benchmark; the
  `market_layer` and approved source policy determine that meaning.
