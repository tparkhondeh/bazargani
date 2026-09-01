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
- **ResearchValidation / ValidationIssue**: policy-versioned data-quality outcome,
  explainable confidence score, and subject-linked warnings/errors.

The current confidence policy starts at 100, subtracts 10 per warning and 30 per
error, and clamps at zero. Any error produces `NEEDS_HUMAN_REVIEW`; warning-only
results produce `NEEDS_VERIFICATION`; only an issue-free result is `PASSED`. The
policy version is stored so later rule changes cannot silently rewrite history.

## Product-match policy

The deterministic baseline normalizes Persian/Arabic character variants and digits,
computes token-set name similarity, then compares explicit requested and observed
attributes. It emits exactly one class per retained price:

- `EXACT_VARIANT`: exact normalized name and every requested attribute supplied and equal.
- `EXACT_PRODUCT`: exact normalized name without an attribute conflict, but the
  variant may be unspecified.
- `COMPARABLE`: name similarity is at least 0.60, at least half of requested
  attributes agree, and none conflict.
- `SIMILAR`: partial name/feature overlap that is insufficient for comparability.
- `SUBSTITUTE`: no material name overlap; generic matching attributes alone cannot
  promote an unrelated product.

Scores are deterministic: without requested attributes, name similarity contributes
100%; otherwise name, attribute agreement, and attribute coverage contribute 60/30/10
points and each conflict subtracts 20. A conflicting feature or substitute escalates
the run to human review; comparable/similar or an unverified variant produces a
verification warning. This lexical baseline is intentionally conservative and will
later be complemented—not overwritten—by evaluated assisted matching.

Important invariants: quantities are positive integers; money uses `Decimal` and an
explicit currency; derived values identify inputs; evidence timestamps are timezone
aware; exact duplicate observations do not enter calculations; research history is
append-only; and product-match class accompanies every comparison.
