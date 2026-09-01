# ADR 0018: Observed quantity analysis without invented EOQ

## Decision

Build quantity analysis only from persisted, evidence-backed price observations. Group
identified offers by supplier, canonical product identity (name, variant, and sorted
attributes), and compatible normalized unit/currency comparison group. Never merge
anonymous observations or distinct product variants. Sort points by quoted quantity
and observation ID.

For adjacent points with comparable normalized prices, calculate the signed percentage
change with `Decimal` and half-up rounding to two places. Preserve original price,
quantity, MOQ, eligibility, source, and normalized value on every point.

Return economic-order-range fields as null and state the missing demand, ordering,
holding, lead-time, service-level, capacity, and negotiation evidence. Do not treat
observed quote quantities as guaranteed continuous tiers. Use the same pure calculation
for the tenant-scoped API and newly generated Persian reports.

## Consequences

- Users can see actual observed quantity/price relationships without silent
  interpolation or supplier mixing.
- Missing FX paths break an adjacent series rather than manufacturing a comparison.
- The output supports future explicit quantity-tier data while remaining honest about
  current evidence limits.
- A true EOQ or economic-order-range model requires a separate input contract, domain
  review, and exact tests before its null fields can be populated.
