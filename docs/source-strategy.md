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

`GET /api/v1/providers` exposes the governed descriptor for authenticated operators.
The ECB descriptor declares its narrow scope, fixed host, cache TTL, limitations,
enabled state, and explicit terms-approval state. An unknown official rate limit is
represented as `null`, never guessed. `TRADE_AGENT_ECB_ENABLED=false` is the shutdown
path and prevents provider construction/network use. Production startup fails closed
when ECB is enabled without `TRADE_AGENT_ECB_TERMS_APPROVED=true`; that assertion may be
set only after a documented authorization/terms decision and does not replace the
separate network-egress review.

The 2026-09-01 source review did not approve a product-price adapter. eBay Browse API
production access is subject to application/approval and API-license restrictions;
Best Buy's Products API requires a key and its published terms constrain how content is
used. Both remain deferred until the intended commercial use, retention/display rules,
and authorization are approved. UN Comtrade remains useful trade-statistics context,
not supplier quote evidence. No scraper or inferred replacement is introduced for any
of these sources.

`GET /api/v1/providers/ecb-fx-reference/health` is a passive operational projection,
not another acquisition path. It reports only actual valid request-driven attempts made
by the current process and never probes the upstream service. Cache hits, failures, and
the latest outcome remain separate; process restart and multi-worker limitations are
explicit.
