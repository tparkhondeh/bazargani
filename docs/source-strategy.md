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

