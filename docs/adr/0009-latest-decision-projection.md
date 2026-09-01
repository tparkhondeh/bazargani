# ADR 0009: Evidence-backed latest-decision projection

## Decision

Represent an opportunity's current decision as a read-time projection of the newest
tenant-owned research run that has an immutable decision report. Return the run's
current lifecycle status, immutable report, validation ledger, ordered landed-cost
scenario summaries, and every supplier-offer ranking with rank 1.

Do not store a separately editable `current_recommendation` string. Such a field could
drift from the report and allow unsupported assertions to appear authoritative. A newer
run without results does not replace the last evidence-backed projection. Equal leading
offers are all returned; the service does not invent a tie-breaker.

## Consequences

- The projection remains traceable to one reproducible research run and report hash.
- Later human review may change the run status while preserving its original validation
  result and report, making both system and human outcomes visible.
- Consumers can show useful current decision data without issuing several race-prone
  reads across different run IDs.
- The join remains tenant-scoped and uses existing opportunity/run/report indexes.
- Report Markdown is untrusted presentation data and requires strict sanitization in a
  future HTML client.
- A future recommendation entity is justified only if it retains source-run lineage,
  explicit actor/derivation semantics, and immutable revisions.
