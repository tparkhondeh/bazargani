# Open Source Evaluation Record

Snapshot date: 2026-09-01. Re-evaluate before adoption; stars alone are not a gate.

| Area | Candidate | License / maturity signal | Decision | Rationale |
|---|---|---|---|---|
| Browser automation | [Microsoft Playwright Python](https://github.com/microsoft/playwright-python) | Apache-2.0; long release history, tests and security policy | WRAP later | Mature browser primitive, but not a sourcing abstraction; isolate behind provider port. |
| Crawl/extraction | [Crawl4AI](https://github.com/unclecode/crawl4ai) | Apache-2.0 with attribution requirements; active releases and recent SSRF hardening | EVALUATE/WRAP later | Useful extraction, but recent security changes make direct exposure inappropriate. |
| Typed AI | [Pydantic AI](https://github.com/pydantic/pydantic-ai) | MIT; stable v2 policy, provider-agnostic, active project | ADAPT later | Good structured model boundary after evaluation dataset exists; unnecessary for deterministic slice. |
| Durable agent workflow | [LangGraph](https://github.com/langchain-ai/langgraph) | MIT; active releases, checkpointing/HITL | DEFER | Capable but premature; explicit application state and DB checkpoints are simpler for MVP. |
| API | FastAPI + Pydantic | MIT ecosystem, mature | ADOPT phase 2 | Thin delivery layer only; domain stays independent. |
| Persistence | PostgreSQL + SQLAlchemy/Alembic | permissive libraries, mature | ADOPT phase 2 | Strong constraints, decimal and append-only audit support. |
| Observability | OpenTelemetry | Apache-2.0, vendor-neutral standard | ADOPT phase 2 | Provider-neutral traces/metrics after API and external calls exist. |
| Entity matching | RapidFuzz | MIT, mature | EVALUATE | Useful deterministic feature; domain-specific weighted match still must be built and tested. |
| FX | ECB/other official feeds | data terms vary | WRAP per feed | Preserve point-in-time source; Iran market rates need separately approved provenance. |
| Marketplace products | [eBay Browse API](https://developer.ebay.com/api-docs/buy/api-browse.html) | OAuth credentials; [Buy API production requirements](https://developer.ebay.com/api-docs/buy/buy-requirements.html) and [API license](https://developer.ebay.com/join/api-license-agreement) apply | DEFER — commercial approval required | Production access and content display/retention/co-mingling constraints require a documented approved use case before an adapter or fixture is built. |
| Retail products | [Best Buy Products API](https://developers.bestbuy.com/apis) | API key; published [API terms](https://developer.bestbuy.com/legal) constrain use and content handling | DEFER — commercial approval required | Product/price capability is relevant, but a generic supplier-comparison use has not been authorized against the published restrictions. |
| HS/trade data | [UN Comtrade](https://unstats.un.org/unsd/trade/) / WITS / national customs | API/data terms vary | EVALUATE | Valuable aggregate trade context, not a supplier quote or authoritative product classification; expert review remains required. |

No dependency is added in slice 1 because the standard library can prove the domain
and calculation seams. A dependency inventory and third-party notices file become a
release gate when the first external package is locked.

Phase 3 adopts the official [ECB Data Portal SDMX API](https://data.ecb.europa.eu/help/api/data)
behind the safe HTTP port. The documented `EXR.D.<currency>.EUR.SP00.A` series provides
daily informational euro reference rates; it does not replace a verified Iranian FX
source or executable dealer quote. Production startup additionally requires an explicit
operator assertion that the ECB terms/authorization review is complete; the assertion
does not itself establish legal approval or authorize network egress.
