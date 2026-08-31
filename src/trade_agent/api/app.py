from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from trade_agent.api.logging import configure_logging
from trade_agent.api.schemas import (
    ErrorBody,
    OpportunityCreate,
    OpportunityView,
    ResearchRunTransition,
    ResearchRunView,
)
from trade_agent.config import Settings, get_settings
from trade_agent.domain.workflow import InvalidTransitionError, VersionConflictError
from trade_agent.infrastructure.database import Base, make_session_factory
from trade_agent.infrastructure.repository import TradeRepository

logger = logging.getLogger("trade_agent.http")


def _correlation_id(value: str | None) -> str:
    if value:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return str(uuid4())


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)
    database_engine = engine or create_engine(resolved.database_url, pool_pre_ping=True)
    sessions = make_session_factory(database_engine)
    repository = TradeRepository(sessions)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        if resolved.auto_create_schema:
            Base.metadata.create_all(database_engine)
        yield
        database_engine.dispose()

    app = FastAPI(
        title="Bazargani Trade Agent API",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.engine = database_engine
    app.state.sessions = sessions
    app.state.repository = repository

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        started = time.perf_counter()
        correlation_id = _correlation_id(request.headers.get("X-Correlation-ID"))
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        logger.info(
            "request_completed",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response

    def error(request: Request, status: int, code: str, message: str) -> JSONResponse:
        body = ErrorBody(
            code=code,
            message=message,
            correlation_id=request.state.correlation_id,
        )
        return JSONResponse(status_code=status, content=body.model_dump())

    @app.exception_handler(KeyError)
    async def not_found(request: Request, exc: KeyError) -> JSONResponse:
        return error(request, 404, "NOT_FOUND", str(exc).strip("'"))

    @app.exception_handler(VersionConflictError)
    async def version_conflict(request: Request, exc: VersionConflictError) -> JSONResponse:
        return error(request, 409, "VERSION_CONFLICT", str(exc))

    @app.exception_handler(InvalidTransitionError)
    async def invalid_transition(request: Request, exc: InvalidTransitionError) -> JSONResponse:
        return error(request, 409, "INVALID_TRANSITION", str(exc))

    def correlation(request: Request) -> str:
        return str(request.state.correlation_id)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        with database_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready", "persistence": "database"}

    @app.post("/api/v1/opportunities", response_model=OpportunityView, status_code=201)
    def create_opportunity(
        payload: OpportunityCreate,
        correlation_id: str = Depends(correlation),
    ) -> Any:
        return repository.create_opportunity(
            product_name=payload.product_name,
            quantity=payload.quantity,
            target_market=payload.target_market,
            correlation_id=correlation_id,
        )

    @app.get("/api/v1/opportunities/{opportunity_id}", response_model=OpportunityView)
    def get_opportunity(opportunity_id: str) -> Any:
        return repository.get_opportunity(opportunity_id)

    @app.post(
        "/api/v1/opportunities/{opportunity_id}/research-runs",
        response_model=ResearchRunView,
        status_code=201,
    )
    def create_run(
        opportunity_id: str,
        correlation_id: str = Depends(correlation),
    ) -> Any:
        return repository.create_research_run(
            opportunity_id=opportunity_id, correlation_id=correlation_id
        )

    @app.post(
        "/api/v1/research-runs/{run_id}/transitions",
        response_model=ResearchRunView,
    )
    def transition_run(
        run_id: str,
        payload: ResearchRunTransition,
        correlation_id: str = Depends(correlation),
    ) -> Any:
        return repository.transition_research_run(
            run_id=run_id,
            target=payload.target_status,
            expected_version=payload.expected_version,
            correlation_id=correlation_id,
        )

    return app


app = create_app()
