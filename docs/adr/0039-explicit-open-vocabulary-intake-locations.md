# ADR 0039: Explicit open-vocabulary intake locations

## Decision

Extend the deterministic Persian/English intake parser beyond its small location
vocabulary, but capture an unknown location only after an explicit origin or destination
marker. Bound each normalized value to 100 characters and preserve it as user-supplied
text. Do not geocode it or claim that it names a real country, city, port, or market.

Keep the existing canonical aliases for supported common locations. Order every match
by its position in the request, normalize aliases, and deduplicate case-insensitively.
If exactly one distinct value remains, return it. If multiple values remain, return no
selected value, expose the ordered candidates in `field_conflicts`, and add a critical
clarification question. Do not create a missing-origin assumption when an origin
conflict is already explicit.

Do not treat a generic unknown English `to` or Persian `به` phrase as sufficient
location syntax; those tokens also occur in product descriptions and action phrases.
Known destination aliases can retain the narrower established shorthand behavior.

## Consequences

- Requests for explicitly marked locations outside the original hard-coded list can
  start without an LLM or external geographic service.
- Conflicting location text blocks automatic start instead of using regex order as an
  implicit commercial decision.
- `field_conflicts` is an additive API field that clients should render as untrusted
  clarification context.
- Syntactic parser confidence is not evidence of geographic validity or deliverability.
- Constraint extraction and assisted parsing remain separate future work; no database
  migration or dependency change is required.
