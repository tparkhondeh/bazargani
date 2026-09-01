from __future__ import annotations

import re
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRADE_AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="development", pattern="^(development|test|production)$")
    log_level: str = "INFO"
    database_url: str = "sqlite+pysqlite:///./data/trade_agent.db"
    auto_create_schema: bool = True
    max_request_body_bytes: int = Field(default=2_000_000, ge=1024, le=10_000_000)
    ecb_enabled: bool = True
    ecb_terms_approved: bool = False
    ecb_cache_ttl_seconds: int = Field(default=3_600, ge=60, le=86_400)
    api_rate_limit_requests: int = Field(default=120, ge=1, le=100_000)
    api_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3_600)
    auth_enabled: bool = False
    api_key_credentials: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_production(self) -> Settings:
        tenant_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
        for digest, tenant_id in self.api_key_credentials.items():
            if re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
                raise ValueError("API key credential identifiers must be SHA-256 hex digests")
            if tenant_pattern.fullmatch(tenant_id) is None:
                raise ValueError("tenant identifiers contain unsupported characters")
        if self.auth_enabled and not self.api_key_credentials:
            raise ValueError("auth_enabled requires at least one API key credential")
        if self.environment == "production":
            if self.database_url.startswith("sqlite"):
                raise ValueError("production requires PostgreSQL")
            if self.auto_create_schema:
                raise ValueError("production schema must be managed by Alembic")
            if not self.auth_enabled:
                raise ValueError("production requires authentication")
            if self.ecb_enabled and not self.ecb_terms_approved:
                raise ValueError(
                    "production cannot enable ECB before explicit terms approval"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
