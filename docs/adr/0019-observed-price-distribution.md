# ADR 0019: Compatible observed-price distributions without benchmark inference

## Decision

Calculate price distributions only from retained, BASE-normalized observations in one
research run. Group by canonical product identity (name, variant, and sorted
attributes), declared market layer, exact quoted quantity, and compatible normalized
unit/currency comparison group. Exclude and identify observations without a normalized
price instead of mixing original currencies or estimating a conversion.

For every non-empty group, return ordered observation IDs, observation count, distinct
source-URL count, minimum, median, maximum, and range. Use `Decimal`; for an even number
of values, average the two center values and round half-up to eight decimal places. Use
the same pure calculation in the tenant-scoped API and newly generated Persian reports.

Treat market layer as a grouping label, not evidence of source approval,
representativeness, Iranian-market coverage, or benchmark validity. Raw evidence stays
outside this decision read model.

## Consequences

- Incompatible products, variants, quantities, units, currencies, and market layers
  cannot create misleading aggregate statistics.
- Missing FX remains visible as an exclusion rather than becoming an invented price.
- Single-observation groups are allowed and transparently show count and zero range;
  consumers can judge the weak coverage without losing the observation.
- A validated Iranian benchmark requires an approved provider, an explicit benchmark
  contract, and representativeness policy before any comparison or spread claim is made.
