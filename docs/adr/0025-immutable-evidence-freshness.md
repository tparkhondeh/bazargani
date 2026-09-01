# ADR 0025: Immutable evidence-freshness projection

## Decision

Create a pure evidence-freshness projection anchored to each research run's persisted
validation timestamp. Share the validator's 30-day maximum age and five-minute future
clock-skew constants with the projection. For every deduplicated evidence row, expose
retrieval time, exact decimal age in seconds, classification, confidence, fingerprint,
source metadata, exact retained price/FX usage count, and an explicit current, allowed-
skew, stale, or future-dated status.

Move canonical evidence fingerprint generation into the same application module so
persistence and report generation deduplicate identical evidence with one algorithm.
Normalize database timestamps to UTC at the repository boundary, retain strict aware-
datetime validation in the pure calculation, and omit raw evidence from both API and
report output.

## Consequences

- Historical freshness results remain reproducible and do not drift with wall-clock
  time.
- API and report classifications cannot diverge from validation age boundaries.
- Usage counts make shared FX evidence visible without duplicating evidence records.
- Freshness remains a review signal only; it does not establish source authority,
  accuracy, independence, legal validity, or commercial fitness.
