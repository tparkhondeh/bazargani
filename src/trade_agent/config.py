from __future__ import annotations

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

    @model_validator(mode="after")
    def validate_production(self) -> Settings:
        if self.environment == "production":
            if self.database_url.startswith("sqlite"):
                raise ValueError("production requires PostgreSQL")
            if self.auto_create_schema:
                raise ValueError("production schema must be managed by Alembic")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
