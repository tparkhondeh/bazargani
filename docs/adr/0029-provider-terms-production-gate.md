# ADR 0029: Fail-closed provider terms gate in production

## Decision

Add a non-secret `ecb_terms_approved` configuration assertion, defaulting to false, and
expose it in the typed provider descriptor. Derive the human-readable ECB review status
from the same value so the API cannot report an approval state that disagrees with the
startup gate.

Reject production configuration when ECB is enabled and the assertion is false. Permit
production startup with ECB disabled so deployment and non-provider functionality can
operate without implying source authorization. Set the assertion to true only after an
operator has retained a documented decision covering the exact service and intended
use. Continue to require independent egress allowlisting, monitoring, and source-policy
review.

Do not add a product-price adapter from the 2026-09-01 candidate review. eBay Browse and
Best Buy Products require production/commercial approval and impose content-use
conditions that have not been approved for this system; UN Comtrade is aggregate trade
context rather than supplier quote evidence.

## Consequences

- An advisory `PENDING_FORMAL_REVIEW` state can no longer coexist with enabled ECB in a
  production process.
- Disabling ECB remains a safe production path and prevents adapter construction or
  network traffic.
- The runtime flag records an operator assertion, not the legal decision itself; audit
  evidence must be retained outside environment configuration.
- New providers need their own typed approval assertion, startup gate, shutdown path,
  and contract tests before production enablement.
- No credentials, scraped data, mock prices, or unverifiable supplier facts enter this
  slice.
