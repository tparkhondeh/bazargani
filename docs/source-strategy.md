# Source Strategy

Acquisition priority: official API, licensed structured feed, public structured data,
search/retrieval provider, browser automation, then narrowly approved scraping.

Every adapter declares source identity, supported markets, terms-review status,
rate limits, retrieval method, data freshness, confidence inputs, and failure modes.
Sources are configured, not embedded in business logic.

Before enabling a provider, record authorization/terms, retention permission,
robots policy where relevant, stable identifiers, sample evidence, contract tests,
and a shutdown path. A provider may never transform an estimate into a fact.

The first slice uses a validated evidence-bundle adapter. This is deliberate: it
lets domain and calculation behavior be exercised with real, user-supplied evidence
without unsafe generic scraping. Automated adapters follow after source approval.

The first live adapter is the official ECB SDMX exchange-rate service. It is limited
to the fixed `data-api.ecb.europa.eu` host, HTTPS/443, disabled redirects/proxies,
public IP resolution, bounded responses, timeouts, and retries. ECB rates are labelled
informational reference rates; they are not Iranian transaction rates. DNS validation
must be paired with production egress allowlisting to fully mitigate rebinding races.

The authenticated API exposes this adapter as an informational EUR reference quote.
It returns the official URL, raw SDMX CSV observation, retrieval/effective timestamps,
evidence class/confidence, and transformation. Successful results use a configurable
60–86,400 second cache (default 3,600); failures return `502 UPSTREAM_UNAVAILABLE` and
never fall back to silently stale data. This endpoint does not provide an Iranian
transaction, remittance, sanctions, customs, or settlement rate.
