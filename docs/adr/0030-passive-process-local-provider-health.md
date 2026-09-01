# ADR 0030: Passive process-local provider health

## Decision

Record runtime health inside the serialized ECB reference-rate cache service, using
only valid client-triggered cache misses. Expose an authenticated passive endpoint with
the explicit states `NOT_OBSERVED`, `LAST_ATTEMPT_SUCCEEDED`,
`LAST_ATTEMPT_FAILED`, and `DISABLED`; reading health must not construct an adapter or
make a network request.

Return timezone-aware observation/attempt/success/failure times and non-negative counts
for upstream attempts, successes, failures, consecutive failures, and cache hits. Keep
cache hits from changing the last upstream outcome. Count adapter-construction and
provider-call failures, but reject invalid currency input before creating an attempt.
Do not expose error type/text, upstream response content, source URLs, or credentials.

Label the projection `PROCESS_LOCAL`, reset it naturally on process restart, and include
limitations stating that cached responses do not revalidate upstream availability and
the last observed outcome is not an SLA or current/fleet-wide reachability guarantee.

## Consequences

- Operators can distinguish an untried provider from an observed success or failure
  without generating extra traffic or consuming an undocumented rate budget.
- Cache behavior and upstream behavior remain measurable without presenting either as
  proof that the provider is currently reachable.
- The same lock that prevents request stampedes makes counters and snapshots consistent
  within a process.
- Production alerting still needs external cross-worker aggregation and retention;
  these counters are intentionally not persisted as commercial evidence.
- Future providers need equivalent passive instrumentation or an explicit
  `NOT_INSTRUMENTED` contract rather than guessed health.
