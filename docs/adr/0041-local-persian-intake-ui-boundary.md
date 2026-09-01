# ADR 0041: Local Persian intake UI boundary

## Decision

Serve a dependency-free Persian RTL intake shell from fixed FastAPI package assets at
`/ui`. Keep the shell public because it contains no tenant data, but send parsing only
to the existing authenticated `POST /api/v1/requests/parse` boundary. Hold an optional
API key only in the page's password field for the current session, clear it on page
exit, and never use browser storage, cookies, query parameters, or logs.

Render every parser-controlled or user-controlled value through DOM text nodes. Apply
a path-scoped Content Security Policy that denies all sources except same-origin
scripts, styles, images, and API connections, and add same-origin opener/resource
policies. Package the three fixed UI assets in distributions so an installed service
does not depend on the source tree or an external CDN.

Limit this slice to deterministic request parsing and clarification. Do not create an
opportunity or research run by chaining multiple client mutations: a later slice must
provide one atomic authenticated application use case before the UI can offer a start
action. The page labels its example as educational input and explicitly states that a
parsed result is not research, price evidence, or an independent fact.

## Consequences

- Local users gain the first working Persian surface without introducing a JavaScript
  build chain or duplicating business rules in the browser.
- A public static shell does not weaken API authentication or tenant isolation.
- CSP, output encoding, and transient credential handling are regression-tested.
- Progress, result, assumptions, history, Markdown rendering, and atomic research start
  remain separate bounded slices.
- Production exposure still requires explicit deployment authorization, trusted TLS,
  backup/rollback preparation, and the identity controls already listed in security
  documentation.
