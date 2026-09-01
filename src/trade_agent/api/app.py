import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, Query, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from trade_agent import __version__
from trade_agent.api.auth import (
    AuthenticatedPrincipal,
    AuthenticationError,
    authenticate_api_key,
)
from trade_agent.api.logging import configure_logging
from trade_agent.api.middleware import RequestBodyLimitMiddleware, correlation_id
from trade_agent.api.rate_limit import RateLimitExceeded, TenantRateLimiter
from trade_agent.api.response_headers import apply_response_security_headers
from trade_agent.api.schemas import (
    AuditEventPageView,
    DecisionReportView,
    ErrorBody,
    EvidenceBundleSubmit,
    OpportunityContextUpdate,
    OpportunityCreate,
    OpportunityDecisionView,
    OpportunityPageView,
    OpportunityTransition,
    OpportunityView,
    ParsedTradeRequestView,
    ParseRequestInput,
    ProductMatchView,
    ReferenceRateView,
    ResearchCompletionView,
    ResearchReviewSubmit,
    ResearchReviewView,
    ResearchRunPageView,
    ResearchRunTransition,
    ResearchRunView,
    ResearchValidationView,
    SupplierOfferRankingView,
    ValidationErrorDetail,
)
from trade_agent.api.validation_errors import safe_validation_details
from trade_agent.application.completion import complete_research_run_from_bundle
from trade_agent.application.pagination import MAX_CURSOR_LENGTH, decode_cursor
from trade_agent.application.reference_rates import (
    CachedReferenceRateService,
    ReferenceRateProvider,
)
from trade_agent.config import Settings, get_settings
from trade_agent.domain.errors import PublicInputError
from trade_agent.domain.workflow import (
    IdempotencyConflictError,
    InvalidTransitionError,
    OpportunityStatus,
    VersionConflictError,
)
from trade_agent.infrastructure.database import Base, make_session_factory
from trade_agent.infrastructure.readiness import (
    DatabaseReadiness,
    ReadinessError,
    check_database_readiness,
)
from trade_agent.infrastructure.repository import TradeRepository
from trade_agent.parsing.request import parse_trade_request
from trade_agent.providers.ecb_fx import EcbFxProvider
from trade_agent.providers.errors import ProviderUnavailableError

logger = logging.getLogger("trade_agent.http")


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    reference_rates: ReferenceRateProvider | None = None,
    api_rate_limiter: TenantRateLimiter | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)
    database_engine = engine or create_engine(resolved.database_url, pool_pre_ping=True)
    sessions = make_session_factory(database_engine)
    repository = TradeRepository(sessions)
    rate_service: ReferenceRateProvider = reference_rates or CachedReferenceRateService(
        EcbFxProvider,
        ttl_seconds=resolved.ecb_cache_ttl_seconds,
    )
    request_limiter = api_rate_limiter or TenantRateLimiter(
        requests_per_window=resolved.api_rate_limit_requests,
        window_seconds=resolved.api_rate_limit_window_seconds,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        if resolved.auto_create_schema:
            Base.metadata.create_all(database_engine)
        yield
        database_engine.dispose()

    app = FastAPI(
        title="Bazargani Trade Agent API",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.engine = database_engine
    app.state.sessions = sessions
    app.state.repository = repository
    app.state.api_rate_limiter = request_limiter
    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=resolved.max_request_body_bytes,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        started = time.perf_counter()
        request_correlation_id = correlation_id(request.headers.get("X-Correlation-ID"))
        request.state.correlation_id = request_correlation_id
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                "request_failed",
                extra={
                    "correlation_id": request_correlation_id,
                    "method": request.method,
                    "path": request.url.path,
                    "error_type": type(exc).__name__,
                },
            )
            response = error(request, 500, "INTERNAL_ERROR", "unexpected server error")
        response.headers["X-Correlation-ID"] = request_correlation_id
        apply_response_security_headers(response, path=request.url.path)
        logger.info(
            "request_completed",
            extra={
                "correlation_id": request_correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response

    def error(
        request: Request,
        status: int,
        code: str,
        message: str,
        details: list[ValidationErrorDetail] | None = None,
    ) -> JSONResponse:
        body = ErrorBody(
            code=code,
            message=message,
            correlation_id=request.state.correlation_id,
            details=details,
        )
        return JSONResponse(status_code=status, content=body.model_dump(exclude_none=True))

    @app.exception_handler(KeyError)
    async def not_found(request: Request, exc: KeyError) -> JSONResponse:
        return error(request, 404, "NOT_FOUND", str(exc).strip("'"))

    @app.exception_handler(AuthenticationError)
    async def authentication_failed(
        request: Request, exc: AuthenticationError
    ) -> JSONResponse:
        response = error(request, 401, "AUTHENTICATION_REQUIRED", str(exc))
        response.headers["WWW-Authenticate"] = "ApiKey"
        return response

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded(
        request: Request, exc: RateLimitExceeded
    ) -> JSONResponse:
        response = error(request, 429, "RATE_LIMIT_EXCEEDED", str(exc))
        response.headers["Retry-After"] = str(exc.retry_after_seconds)
        return response

    @app.exception_handler(ReadinessError)
    async def readiness_failed(request: Request, exc: ReadinessError) -> JSONResponse:
        response = error(request, 503, "NOT_READY", str(exc))
        response.headers["Retry-After"] = "5"
        return response

    @app.exception_handler(VersionConflictError)
    async def version_conflict(request: Request, exc: VersionConflictError) -> JSONResponse:
        return error(request, 409, "VERSION_CONFLICT", str(exc))

    @app.exception_handler(IdempotencyConflictError)
    async def idempotency_conflict(
        request: Request, exc: IdempotencyConflictError
    ) -> JSONResponse:
        return error(request, 409, "IDEMPOTENCY_CONFLICT", str(exc))

    @app.exception_handler(InvalidTransitionError)
    async def invalid_transition(request: Request, exc: InvalidTransitionError) -> JSONResponse:
        return error(request, 409, "INVALID_TRANSITION", str(exc))

    @app.exception_handler(PublicInputError)
    async def public_invalid_input(request: Request, exc: PublicInputError) -> JSONResponse:
        return error(request, 422, "INVALID_INPUT", str(exc))

    @app.exception_handler(ValueError)
    async def invalid_input(request: Request, _: ValueError) -> JSONResponse:
        return error(request, 422, "INVALID_INPUT", "request input is invalid")

    @app.exception_handler(ProviderUnavailableError)
    async def provider_unavailable(
        request: Request, exc: ProviderUnavailableError
    ) -> JSONResponse:
        return error(request, 502, "UPSTREAM_UNAVAILABLE", str(exc))

    @app.exception_handler(RequestValidationError)
    async def request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error(
            request,
            422,
            "REQUEST_VALIDATION_FAILED",
            "request validation failed",
            safe_validation_details(exc),
        )

    def correlation(request: Request) -> str:
        return str(request.state.correlation_id)

    def principal(
        api_key: Annotated[str | None, Security(api_key_header)],
    ) -> AuthenticatedPrincipal:
        authenticated = authenticate_api_key(resolved, api_key)
        request_limiter.check(authenticated.tenant_id)
        return authenticated

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> DatabaseReadiness:
        return check_database_readiness(
            database_engine,
            require_migration_head=not resolved.auto_create_schema,
        )

    @app.post("/api/v1/requests/parse", response_model=ParsedTradeRequestView)
    def parse_request(
        payload: ParseRequestInput,
        _principal: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        parsed = parse_trade_request(payload.text)
        return {
            "original_text": parsed.original_text,
            "normalized_text": parsed.normalized_text,
            "product_name": parsed.product_name,
            "quantity": parsed.quantity,
            "quantity_unit": parsed.quantity_unit,
            "origin_market": parsed.origin_market,
            "destination": parsed.destination,
            "field_confidence": parsed.field_confidence,
            "assumptions": parsed.assumptions,
            "critical_questions": parsed.critical_questions,
            "can_start_research": parsed.can_start_research,
        }

    @app.get(
        "/api/v1/reference-rates/ecb/{quote_currency}",
        response_model=ReferenceRateView,
    )
    def get_ecb_reference_rate(
        quote_currency: str,
        _principal: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        return rate_service.latest_reference_rate(quote_currency)

    @app.post("/api/v1/opportunities", response_model=OpportunityView, status_code=201)
    def create_opportunity(
        payload: OpportunityCreate,
        correlation_id: Annotated[str, Depends(correlation)],
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        return repository.create_opportunity(
            product_name=payload.product_name,
            quantity=payload.quantity,
            target_market=payload.target_market,
            correlation_id=correlation_id,
            tenant_id=authenticated.tenant_id,
            actor_id=authenticated.actor_id,
        )

    @app.get("/api/v1/opportunities", response_model=OpportunityPageView)
    def list_opportunities(
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
        status: Annotated[OpportunityStatus | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        after: Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)] = None,
    ) -> Any:
        items, next_cursor = repository.list_opportunities(
            tenant_id=authenticated.tenant_id,
            status=status,
            limit=limit,
            after=decode_cursor(after),
        )
        return {"items": items, "next_cursor": next_cursor}

    @app.get("/api/v1/audit-events", response_model=AuditEventPageView)
    def list_audit_events(
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        after: Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)] = None,
    ) -> Any:
        items, next_cursor = repository.list_audit_events(
            tenant_id=authenticated.tenant_id,
            limit=limit,
            after=decode_cursor(after),
        )
        return {"items": items, "next_cursor": next_cursor}

    @app.get("/api/v1/opportunities/{opportunity_id}", response_model=OpportunityView)
    def get_opportunity(
        opportunity_id: str,
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        return repository.get_opportunity(
            opportunity_id,
            tenant_id=authenticated.tenant_id,
        )

    @app.post(
        "/api/v1/opportunities/{opportunity_id}/transitions",
        response_model=OpportunityView,
    )
    def transition_opportunity(
        opportunity_id: str,
        payload: OpportunityTransition,
        correlation_id: Annotated[str, Depends(correlation)],
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        return repository.transition_opportunity(
            opportunity_id=opportunity_id,
            target=payload.target_status,
            expected_version=payload.expected_version,
            correlation_id=correlation_id,
            tenant_id=authenticated.tenant_id,
            actor_id=authenticated.actor_id,
        )

    @app.patch(
        "/api/v1/opportunities/{opportunity_id}/context",
        response_model=OpportunityView,
    )
    def update_opportunity_context(
        opportunity_id: str,
        payload: OpportunityContextUpdate,
        correlation_id: Annotated[str, Depends(correlation)],
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        changes: dict[str, str | datetime | None] = {}
        for field in ("next_action", "deadline", "notes"):
            if field in payload.model_fields_set:
                changes[field] = getattr(payload, field)
        return repository.update_opportunity_context(
            opportunity_id=opportunity_id,
            expected_version=payload.expected_version,
            changes=changes,
            correlation_id=correlation_id,
            tenant_id=authenticated.tenant_id,
            actor_id=authenticated.actor_id,
        )

    @app.get(
        "/api/v1/opportunities/{opportunity_id}/latest-decision",
        response_model=OpportunityDecisionView,
    )
    def get_latest_opportunity_decision(
        opportunity_id: str,
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        return repository.get_latest_opportunity_decision(
            opportunity_id,
            tenant_id=authenticated.tenant_id,
        )

    @app.post(
        "/api/v1/opportunities/{opportunity_id}/research-runs",
        response_model=ResearchRunView,
        status_code=201,
    )
    def create_run(
        opportunity_id: str,
        correlation_id: Annotated[str, Depends(correlation)],
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        return repository.create_research_run(
            opportunity_id=opportunity_id,
            correlation_id=correlation_id,
            tenant_id=authenticated.tenant_id,
            actor_id=authenticated.actor_id,
        )

    @app.get(
        "/api/v1/opportunities/{opportunity_id}/research-runs",
        response_model=ResearchRunPageView,
    )
    def list_runs(
        opportunity_id: str,
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        after: Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)] = None,
    ) -> Any:
        items, next_cursor = repository.list_research_runs(
            opportunity_id=opportunity_id,
            tenant_id=authenticated.tenant_id,
            limit=limit,
            after=decode_cursor(after),
        )
        return {"items": items, "next_cursor": next_cursor}

    @app.post(
        "/api/v1/research-runs/{run_id}/transitions",
        response_model=ResearchRunView,
    )
    def transition_run(
        run_id: str,
        payload: ResearchRunTransition,
        correlation_id: Annotated[str, Depends(correlation)],
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        return repository.transition_research_run(
            run_id=run_id,
            target=payload.target_status,
            expected_version=payload.expected_version,
            correlation_id=correlation_id,
            tenant_id=authenticated.tenant_id,
            actor_id=authenticated.actor_id,
        )

    @app.post(
        "/api/v1/research-runs/{run_id}/reviews",
        response_model=ResearchReviewView,
        status_code=201,
    )
    def record_research_review(
        run_id: str,
        payload: ResearchReviewSubmit,
        correlation_id: Annotated[str, Depends(correlation)],
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        return repository.record_research_review(
            run_id=run_id,
            decision=payload.decision,
            rationale=payload.rationale,
            expected_version=payload.expected_version,
            correlation_id=correlation_id,
            tenant_id=authenticated.tenant_id,
            actor_id=authenticated.actor_id,
        )

    @app.get(
        "/api/v1/research-runs/{run_id}/reviews",
        response_model=list[ResearchReviewView],
    )
    def get_research_reviews(
        run_id: str,
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        return repository.get_research_reviews(
            run_id,
            tenant_id=authenticated.tenant_id,
        )

    @app.post(
        "/api/v1/research-runs/{run_id}/evidence-bundle",
        response_model=ResearchCompletionView,
    )
    def submit_evidence_bundle(
        run_id: str,
        payload: EvidenceBundleSubmit,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=128,
                pattern=r"^[A-Za-z0-9._:-]+$",
            ),
        ],
        correlation_id: Annotated[str, Depends(correlation)],
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        return complete_research_run_from_bundle(
            repository,
            run_id=run_id,
            bundle=payload.bundle,
            expected_version=payload.expected_version,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            tenant_id=authenticated.tenant_id,
            actor_id=authenticated.actor_id,
        )

    @app.get(
        "/api/v1/research-runs/{run_id}/report",
        response_model=DecisionReportView,
    )
    def get_research_report(
        run_id: str,
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        return repository.get_research_report(
            run_id,
            tenant_id=authenticated.tenant_id,
        )

    @app.get(
        "/api/v1/research-runs/{run_id}/validation",
        response_model=ResearchValidationView,
    )
    def get_research_validation(
        run_id: str,
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        return repository.get_research_validation(
            run_id,
            tenant_id=authenticated.tenant_id,
        )

    @app.get(
        "/api/v1/research-runs/{run_id}/product-matches",
        response_model=list[ProductMatchView],
    )
    def get_product_matches(
        run_id: str,
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        return repository.get_product_matches(
            run_id,
            tenant_id=authenticated.tenant_id,
        )

    @app.get(
        "/api/v1/research-runs/{run_id}/supplier-offer-rankings",
        response_model=list[SupplierOfferRankingView],
    )
    def get_supplier_offer_rankings(
        run_id: str,
        authenticated: Annotated[AuthenticatedPrincipal, Depends(principal)],
    ) -> Any:
        return repository.get_supplier_offer_rankings(
            run_id,
            tenant_id=authenticated.tenant_id,
        )

    return app


app = create_app()
