# Domain Model

- **Opportunity**: commercial lifecycle aggregate and current recommendation.
- **ResearchRun**: immutable point-in-time execution and reproducibility boundary.
- **Product / ProductVariant**: canonical identity and comparison attributes.
- **Source / Evidence**: origin, retrieval time, classification, raw value, and
  transformation lineage.
- **PriceObservation**: source-backed offer or benchmark with quantity and terms.
- **Supplier / Quote / QuantityTier**: commercial counterpart and offer structure.
- **FXRate**: point-in-time conversion edge with rate type and provenance.
- **LandedCostScenario**: named assumptions, component ledger, total and per-unit.
- **Assumption / Unknown**: editable input or unresolved information, never a fact.
- **Recommendation**: derived decision plus confidence, risks, and next action.
- **AuditEvent**: append-only record of actor, action, object, and correlation IDs.

Important invariants: quantities are positive integers; money uses `Decimal` and an
explicit currency; derived values identify inputs; evidence timestamps are timezone
aware; research history is append-only; and product-match class accompanies every
comparison.

