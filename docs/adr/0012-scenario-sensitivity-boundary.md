# ADR 0012: Comparable-basis scenario sensitivity

## Decision

Calculate sensitivity from exactly one optimistic, base, and conservative landed-cost
scenario using `Decimal`. Expose the per-unit values, signed optimistic/conservative
deltas from base, their percentages, and the full per-unit range. Percentage values use
base as denominator and round half-up to two decimal places.

Require identical quantity and target currency before producing comparison numbers.
Return `MIXED_BASIS` with null numeric fields when either basis differs. If base is
zero, retain the per-unit amounts and absolute deltas but return `ZERO_BASE` with null
percentages. Use the same pure calculation in generated reports and the read-time
latest-decision projection.

Do not label this result economic order quantity, an observed market interval, or an
independent risk forecast. It measures the combined effect of the submitted scenario
assumptions only.

## Consequences

- Consumers receive deterministic, reproducible comparisons without reimplementing
  financial formulas.
- Incompatible scenarios cannot produce plausible-looking but invalid percentages.
- Existing report snapshots remain immutable; the richer section applies to newly
  generated reports, while the latest-decision view derives from persisted scenarios.
- Quantity optimization requires explicit carrying, ordering, demand, lead-time, and
  tier evidence in a separate future model.
