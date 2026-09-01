# ADR 0010: Treat generated Markdown as untrusted output

## Decision

Encode every input-derived string before placing it in a Markdown decision report.
Plain text is flattened to one line, HTML-encoded, and Markdown-escaped. Inline-code
values use a fence longer than any embedded backtick and are HTML-encoded. Evidence
link targets are restricted by the domain to HTTP(S) and percent-encoded before being
placed in link syntax.

Keep client rendering as a separate security boundary. A future HTML client must
disable raw HTML or sanitize with a narrow allowlist and apply safe external-link
attributes. Escaping during report generation is defense in depth and makes the stored
Markdown structurally predictable; it is not a substitute for renderer controls.

Existing report rows remain immutable and are not silently rewritten. The strengthened
policy applies to newly generated report snapshots and therefore produces a different
content hash when hostile/special input would previously have altered Markdown syntax.

## Consequences

- Source names, notes, cost labels, supplier names, and product text cannot inject
  headings, HTML, or additional Markdown links into new reports.
- Valid provenance URLs remain usable while delimiters/newlines are encoded inside the
  original HTTP(S) target.
- Stored report hashes continue to describe exact immutable content.
- Renderer sanitization and Content Security Policy remain mandatory for the future UI.
