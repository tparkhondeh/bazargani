# ADR 0026: Structured Incoterm named place and declared version

## Decision

Extend immutable price observations with nullable `incoterm_named_place` and
`incoterm_version` fields through migration `20260901_0011`. Normalize the Incoterm code
to uppercase and trim all three fields, reject unsafe/control or overlong values, and
never supply a default named place or version. Preserve legacy rows as null.

Include both fields in observation deduplication, persistence, evidence-backed price and
supplier-offer views, Incoterm coverage, and newly generated Persian reports. Split the
existing three commercial-completeness points equally across code, named place, and
version. When at least one term is declared but the triplet is incomplete, emit one
`INCOMPLETE_INCOTERM_TERMS` warning listing the exact missing field names.

Keep comparison at `WITHHELD_NO_INCOTERM_SCENARIOS`. A complete declaration is retained
metadata, not proof of negotiated wording and not a substitute for comparable route-
specific cost allocation, operational control, risk-transfer, or legal review.

## Consequences

- Offers with the same code but different named places or versions are no longer
  accidentally deduplicated as identical terms.
- API consumers can display the original commercial declaration without parsing free
  text or assuming Incoterms 2020.
- Incomplete terms become one explainable verification gap instead of silently earning
  full commercial-completeness credit.
- Migration rollback loses only the two new nullable fields and must be preceded by the
  normal backup/export process if those values matter operationally.
