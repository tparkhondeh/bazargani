# ADR 0023: Trade-cost coverage without inferred applicability

## Decision

Create a pure trade-cost coverage projection over immutable landed-cost components.
Maintain a transparent reference vocabulary for product, origin, packaging, inspection,
documentation, inland/export/freight, insurance, tariff/tax/import, port/clearance,
storage, payment/FX/sanctions, domestic transport, contingency, and other explicit cost
codes.

For each scenario, expose exact recorded codes, recognized reference codes, unrecorded
reference codes, custom/unclassified codes, zero-amount codes, total component count,
and counts for `FACT`, `ESTIMATE`, `ASSUMPTION`, `DERIVED_CALCULATION`, and
`AI_INFERENCE`. Preserve optimistic/base/conservative ordering and reject duplicate
scenario names or unknown evidence classes.

Use the same calculation in the tenant-scoped API and newly generated Persian reports.
Do not assign a completeness percentage, infer a missing amount, reject custom codes,
or claim that every reference category is required or applicable.

## Consequences

- Users can see which cost families were explicitly modeled without inspecting formulas
  one by one.
- Custom domain-specific costs remain visible instead of being silently coerced into a
  possibly incorrect category.
- “Unrecorded” is a review prompt only; product, route, Incoterm, law, and expert input
  determine whether a category applies.
- Exact tariff, tax, customs, sanctions, and payment correctness still requires verified
  evidence and specialist review.
