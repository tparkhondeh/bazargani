# MVP Product Specification

## Outcome

Answer one decision well: for a specified product and quantity, which supported
suppliers and terms are credible, what is the reproducible landed cost to the
named destination, how does it compare with the target market, and what remains
unknown or requires human verification?

## Primary workflow

1. Accept a Persian or English request and extract product, quantity, origin,
   destination, constraints, and missing critical fields.
2. Create an immutable research run under an opportunity.
3. Acquire observations through configured source adapters.
4. retain raw facts and provenance; normalize without overwriting originals.
5. classify product match and evidence quality, validate, and deduplicate.
6. construct quantity, incoterm, FX, and cost scenarios.
7. calculate landed cost deterministically and produce an evidence-linked report.
8. allow a human to correct assumptions and explicitly recalculate dependants.

## MVP functional requirements

- Every material value is `FACT`, `ESTIMATE`, `ASSUMPTION`,
  `DERIVED_CALCULATION`, or `AI_INFERENCE`.
- A price requires source URL, retrieval timestamp, currency, unit, quantity or
  tier context, product variant, and confidence label.
- Original values remain immutable; normalized values record transformation.
- FX is point-in-time and tied to a source and rate type.
- Calculations expose every component and use decimal arithmetic.
- Three scenarios are supported without silently changing evidence.
- Provider failure produces partial results and explicit data gaps.
- A low-confidence or incomplete result is marked `NEEDS_VERIFICATION` or
  `NEEDS_HUMAN_REVIEW`.
- Completing or rejecting a review-required result records the authenticated actor,
  rationale, decision, tenant, and exact run version without rewriting evidence.
- Opportunity lifecycle changes follow an explicit version-checked policy, preserve
  actor/correlation attribution in an append-only audit event, and cannot silently
  reopen a won or lost aggregate.
- Opportunity next action, deadline, and notes are tenant-scoped, partially editable,
  version-checked, and explicitly clearable without copying their commercial content
  into audit payloads.
- An opportunity exposes its newest evidence-backed decision without treating a newer
  empty run as a result or discarding equal first-ranked supplier offers.
- Supplier ranking output retains the original commercial offer context and source
  provenance alongside normalized score data, without copying raw evidence bodies.

## Deferred from MVP

Full CRM/ERP, autonomous purchasing, negotiation, RFQ messaging, shipment
tracking, accounting, inventory, automatic customs classification, universal
scraping, and end-user OIDC/role management. Hashed API-key authentication and tenant
isolation are included with the current network API baseline.

## Missing decisions and risks

- Legal entity, target countries, data-processing obligations, and commercial
  terms-of-use review for each source are not yet supplied.
- Iran tariff, licensing, sanctions, payment, and customs inputs require verified
  domain specialists; the system must represent them as unknown until supplied.
- A canonical money display policy (IRR versus toman) must be approved; storage
  uses ISO-like currency codes and never conflates the two.
- Production retention, backup RPO/RTO, user roles, and model-provider policy
  need stakeholder decisions before launch.
- Initial server inventory found an empty target project directory, an unrelated PM2
  application that must remain untouched, and a system Python version below the
  project requirement. No production deployment is authorized until an isolated
  runtime, proxy/TLS settings, backups, and rollback are approved and reconciled.

## Definition of done

The full MVP is done when a real request can execute against multiple compliant
sources, preserve evidence, match products, rank supplier candidates, calculate
tested scenarios, compare an Iranian benchmark, expose assumptions/unknowns and
confidence, persist an audit trail, and render a usable Persian report.
