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
- Evidence metadata remains traceable to every price/FX use through a content
  fingerprint, while decision-oriented API views avoid duplicating raw source bodies.
- Evidence freshness is measured against the immutable validation timestamp with the
  same stale/future thresholds used by validation; exact age and usage counts remain
  visible, and freshness is never presented as source trust or correctness.
- A price requires source URL, retrieval timestamp, currency, unit, quantity or
  tier context, product variant, and confidence label.
- When any Incoterm term is declared, code, named place, and declared version are
  preserved as separate fields; partial terms are surfaced for verification and no
  missing field receives a default.
- Per-offer terms coverage lists declared and missing fields from the current structured
  contract and separately lists material commercial terms that the schema cannot yet
  represent; it produces no completeness percentage or verification claim.
- Payment terms, payment method, timezone-aware quote validity, and positive whole-day
  lead time are optional evidence-bound offer fields. Missing values remain unknown,
  and a quote expired at the run's immutable validation time requires verification.
- Original values remain immutable; normalized values record transformation.
- Structured price observations keep original offer/product/source context beside the
  BASE-scenario normalized comparison and product-match result.
- FX is point-in-time and tied to a source, rate type, and exact consuming scenario;
  scenarios may explicitly use different evidence-classified FX inputs.
- Calculations expose every component and use decimal arithmetic.
- Scenario cost coverage distinguishes recorded reference components, unrecorded
  reference categories, custom codes, zero amounts, and evidence-class counts without
  treating absence as applicability or manufacturing a missing amount.
- Structured run results expose scenario totals, component amounts, currency,
  evidence class, and formula without requiring Markdown parsing or copying raw evidence.
- Three scenarios are supported without silently changing evidence.
- Quantity analysis compares only observed points with the same supplier, canonical
  product/variant identity, and compatible normalized units/currencies, and withholds
  EOQ when its required economic inputs are absent.
- Price distributions calculate exact minimum, median, maximum, and range only among
  observations with identical canonical product identity, quantity, normalized unit/
  currency group, and declared market layer; excluded prices and source coverage remain
  explicit, and no layer label is treated as proof of a market benchmark.
- Incoterm coverage distinguishes recognized declarations, unrecognized codes, and
  observations with no declared code. It counts named-place/version completeness but
  withholds comparison until route-specific cost, control, and risk scenarios are
  captured and comparable.
- Scenario sensitivity exposes exact per-unit deltas and percentages only when all
  three scenarios share quantity and target currency; it never masquerades as EOQ.
- Provider failure produces partial results and explicit data gaps.
- A low-confidence or incomplete result is marked `NEEDS_VERIFICATION` or
  `NEEDS_HUMAN_REVIEW`.
- Persisted validation issues and individually declared unknowns are exposed as a
  tenant-scoped structured data-gap summary; an empty recorded set is never presented
  as proof of commercial completeness.
- Completing or rejecting a review-required result records the authenticated actor,
  rationale, decision, tenant, and exact run version without rewriting evidence; the
  audit event omits rationale while the role-authorized review ledger retains it.
- Generic audit reads expose only the defined public fields for review actions, including
  historical events, without modifying the append-only stored payload.
- Review queues, review histories, and review writes fail closed unless the calling
  credential has the exact reviewer role; role authorization never replaces the
  independent tenant predicate or claims a named human identity.
- Opportunity lifecycle changes follow an explicit version-checked policy, preserve
  actor/correlation attribution in an append-only audit event, and cannot silently
  reopen a won or lost aggregate.
- Opportunity next action, deadline, and notes are tenant-scoped, partially editable,
  version-checked, and explicitly clearable without copying their commercial content
  into audit payloads.
- An opportunity exposes its newest evidence-backed decision without treating a newer
  empty run as a result or discarding equal first-ranked supplier offers.
- A run-level executive summary exposes conservative review/recommendation codes,
  all leading unverified supplier candidates, BASE landed cost, confidence, and data-gap
  context, while withholding Iranian market price and gross spread until a comparable
  benchmark source is explicitly approved.
- Supplier ranking output retains the original commercial offer context and source
  provenance alongside normalized score data, without copying raw evidence bodies.
- Supplier evidence coverage aggregates offer/source counts and MOQ/Incoterm/rankable
  field coverage without merging anonymous offers or claiming identity, source
  independence, certifications, capacity, or due-diligence verification.
- A supplier legal-identity claim is optional, immutable, tied to one exact retained
  offer and its own evidence, and begins `UNREVIEWED`; its legal name, jurisdiction,
  or registration number never overwrites the quoted supplier name, changes ranking,
  creates a supplier profile, or proves due diligence. Separate append-only reviews
  may describe the evidence as supported, contradicted, or inconclusive, but never
  label the identity verified or mutate the original report snapshot.
- Assumptions and unknowns remain distinct, bounded, tenant-scoped run snapshots and
  are visible in the current decision without permitting historical mutation.
- A correction creates an idempotent tenant-scoped successor linked to a report-bearing
  source run under an expected-version lock. It copies no evidence or result rows; the
  corrected full bundle is recalculated normally, while the predecessor report/hash
  remains unchanged and visible in history.
- The review worklist contains only tenant-owned, offer-scoped identity claims whose
  latest append-only state is `UNREVIEWED` or `INCONCLUSIVE`; resolved claims disappear
  without erasing history, and queue membership never asserts verified identity.
- Report-bearing research runs in a system-derived reviewable status appear in a bounded
  tenant worklist with current version, report hash, validation lineage, confidence, and
  deterministic gap counts; sensitive bodies and review rationale remain outside it.
- Generated report text cannot let untrusted product/source/note fields inject HTML,
  headings, or additional links; client rendering remains separately sanitized.
- Every automated provider exposes controlled scope/limitations/terms status and a
  tested kill switch; unknown operational policy is represented explicitly, not guessed.
- Production startup rejects an enabled automated provider without an explicit,
  documented terms-approval assertion; runtime approval flags do not replace the
  underlying authorization record or network-egress review.
- Provider health reads are authenticated and passive, distinguish unobserved/disabled
  state from real attempt outcomes, expose no exception content, and never claim a
  process-local historical observation proves current or fleet-wide availability.

## Deferred from MVP

Full CRM/ERP, autonomous purchasing, negotiation, RFQ messaging, shipment
tracking, accounting, inventory, automatic customs classification, universal
scraping, and end-user OIDC/named-user role management. Hashed API-key authentication,
credential-level reviewer roles, and tenant isolation are included with the current
network API baseline.

## Missing decisions and risks

- Legal entity, target countries, data-processing obligations, and commercial
  terms-of-use review for each source are not yet supplied.
- Iran tariff, licensing, sanctions, payment, and customs inputs require verified
  domain specialists; the system must represent them as unknown until supplied.
- A canonical money display policy (IRR versus toman) must be approved; storage
  uses ISO-like currency codes and never conflates the two.
- Production retention, backup RPO/RTO, named-user roles, and model-provider policy
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
