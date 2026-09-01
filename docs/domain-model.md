# Domain Model

- **Opportunity**: commercial lifecycle aggregate and current recommendation.
- **ResearchRun**: immutable point-in-time execution and reproducibility boundary.
- **Product / ProductVariant**: canonical identity and comparison attributes.
- **Source / Evidence**: origin, retrieval time, classification, raw value, and
  transformation lineage.
- **PriceObservation**: source-backed offer or benchmark with quantity and terms.
- **Supplier / Quote / QuantityTier**: commercial counterpart and offer structure.
- **FXRate**: point-in-time conversion edge with rate type and provenance.
- **LandedCostScenario**: named assumptions, component ledger, total and per-unit.
- **Assumption / Unknown**: editable input or unresolved information, never a fact.
- **Recommendation**: derived decision plus confidence, risks, and next action.
- **AuditEvent**: append-only record of actor, action, object, and correlation IDs.
- **ResearchValidation / ValidationIssue**: policy-versioned data-quality outcome,
  explainable confidence score, and subject-linked warnings/errors.
- **ResearchReview**: append-only approve/reject decision with rationale, actor
  fingerprint, tenant, and exact before/after run status and version.

Opportunity lifecycle transitions are explicit: `RESEARCHING` can move to `SOURCING`,
`ON_HOLD`, or `LOST`; sourcing can progress to negotiation or evaluation; negotiation
and evaluation can move between each other and close as won/lost; and an on-hold item
must resume into a named active stage. `WON` and `LOST` are terminal, and self-
transitions are rejected. This is the initial workflow policy, not verified commercial
fact; ADR 0007 records the assumptions requiring stakeholder validation.

An opportunity also carries mutable workflow context: an optional next action,
timezone-aware deadline, and notes. Context changes increment the same aggregate
version as status changes. The audit trail records which fields changed, but not their
potentially sensitive values; the current row remains the source of truth for context.

The current decision is a read projection, not independently editable state. It selects
the newest research run with an immutable decision report and returns its validation,
landed-cost summaries, and all leading offer rows. The run's current workflow status
may reflect a later human review while the underlying validation/report stay immutable.

The current confidence policy starts at 100, subtracts 10 per warning and 30 per
error, and clamps at zero. Any error produces `NEEDS_HUMAN_REVIEW`; warning-only
results produce `NEEDS_VERIFICATION`; only an issue-free result is `PASSED`. The
policy version is stored so later rule changes cannot silently rewrite history.

## Product-match policy

The deterministic baseline normalizes Persian/Arabic character variants and digits,
computes token-set name similarity, then compares explicit requested and observed
attributes. It emits exactly one class per retained price:

- `EXACT_VARIANT`: exact normalized name and every requested attribute supplied and equal.
- `EXACT_PRODUCT`: exact normalized name without an attribute conflict, but the
  variant may be unspecified.
- `COMPARABLE`: name similarity is at least 0.60, at least half of requested
  attributes agree, and none conflict.
- `SIMILAR`: partial name/feature overlap that is insufficient for comparability.
- `SUBSTITUTE`: no material name overlap; generic matching attributes alone cannot
  promote an unrelated product.

Scores are deterministic: without requested attributes, name similarity contributes
100%; otherwise name, attribute agreement, and attribute coverage contribute 60/30/10
points and each conflict subtracts 20. A conflicting feature or substitute escalates
the run to human review; comparable/similar or an unverified variant produces a
verification warning. This lexical baseline is intentionally conservative and will
later be complemented—not overwritten—by evaluated assisted matching.

## Supplier-offer ranking policy

Rankings compare offers only inside the same price unit and normalized target
currency. The baseline score is capped at 100 and consists of:

- product match: 35 points;
- evidence classification and confidence: 20 points;
- quantity/MOQ fit: 10 points;
- commercial-field completeness: 10 points;
- relative normalized price: 25 points.

When a group contains only one rankable offer, price receives a neutral 12/25 rather
than an unsupported “best price” score. Offers below MOQ, without supplier identity,
without an FX path, with a substitute product,
or with conflicting product attributes remain visible but can be marked unrankable.
Equal total score and normalized price receive the same rank. Supplier reliability,
certifications, capacity, and payment terms remain explicit unknowns until supported
by evidence; the ranking therefore evaluates the submitted offer, not supplier trust.

Every persisted ranking read is joined back to its price observation and evidence. A
consumer receives original price/currency, quoted quantity/unit, MOQ, Incoterm, source,
retrieval time, evidence classification/confidence, and transformation with the score.
This is an evidence-backed offer view, not a supplier verification profile.

## Scenario-sensitivity policy

Sensitivity compares exactly one `OPTIMISTIC`, `BASE`, and `CONSERVATIVE` scenario.
It reports each per-unit amount, optimistic and conservative deltas from base, and the
full per-unit range. Percentages use `Decimal`, round half-up to two decimal places,
and use the base per-unit amount as denominator.

All three scenario quantities and target currencies must match. Otherwise the result
is `MIXED_BASIS` and contains no comparison amounts or percentages. A zero base retains
the comparable amounts and absolute deltas but returns `ZERO_BASE` with no undefined
percentages. These deltas combine every submitted price, cost, and contingency
assumption; they are not an economic order quantity calculation or an independently
observed market range.

The landed-cost ledger is a read model over persisted scenarios and calculated
components. It preserves the scenario basis, total/per-unit values, component currency,
evidence class, and formula. It does not embed raw source bodies, and it does not permit
clients to mutate or recalculate an immutable research run.

Every persisted FX rate belongs to one landed-cost scenario. A shared bundle rate is
expanded into explicit optimistic/base/conservative lineage; an optional scenario
`fx_rates` collection overrides the shared collection. Pair, rate type, and effective
time must be unique inside a scenario, including when effective time is absent. The
exact rate and evidence remain distinct across scenarios, so a scenario assumption is
never silently relabelled as a shared fact.

Research assumptions and unknowns are separate immutable note collections. API views
normalize them into deterministic text order and expose them both at run level and in
the latest opportunity decision. They are not opportunity workflow notes and cannot be
patched in place. A correction belongs to a new research run whose dependant results
are explicitly recalculated.

The evidence catalog is a read projection over immutable, deduplicated evidence. Each
entry has a SHA-256 fingerprint and one or more deterministic usage references:
`PRICE_OBSERVATION` points to the external observation ID and `FX_RATE` identifies the
scenario/pair/type/effective time. Fingerprints are integrity identifiers, not source
trust scores. Raw evidence remains stored for controlled future review but is not
returned by this general decision API.

The evidence-backed price-observation view joins the immutable observation to its
source, product match, and supplier-ranking normalization. Original amount/currency
remain authoritative source values. `normalized_amount` is the deterministic BASE-
scenario currency conversion used for comparison and may be null when no FX path
exists; it is not an independently observed price.

Quantity analysis groups observations by identified supplier, canonical product name/
variant/attributes, and comparison group. Anonymous observations and distinct variants
remain separate. Points are ordered by quoted quantity, and an adjacent normalized-
price change is calculated only when both comparable values exist.
The status distinguishes no observations, no comparable prices, and observed quotes.
Economic order range stays null because observed quotes alone do not provide demand,
ordering cost, holding cost, lead time, service level, or capacity evidence.

Important invariants: quantities are positive integers; money uses `Decimal` and an
explicit currency; derived values identify inputs; evidence timestamps are timezone
aware; exact duplicate observations do not enter calculations; research history is
append-only; scenario names are unique per case; and product-match class accompanies
every comparison.

Manual status transitions cannot claim validation outcomes or completion. A run in
`NEEDS_VERIFICATION`, `NEEDS_HUMAN_REVIEW`, or `PARTIAL` becomes `COMPLETED` only via
an `APPROVE` review and becomes `CANCELLED` via `REJECT`. Rejection is terminal for
that immutable run; further research starts in a new run instead of overwriting the
existing evidence and report.
