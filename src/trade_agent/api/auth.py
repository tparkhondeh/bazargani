from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from trade_agent.config import Settings


class AuthenticationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    tenant_id: str
    actor_id: str


def authenticate_api_key(settings: Settings, api_key: str | None) -> AuthenticatedPrincipal:
    if not settings.auth_enabled:
        return AuthenticatedPrincipal(
            tenant_id="local-development",
            actor_id="development-auth-disabled",
        )
    if api_key is None or not 32 <= len(api_key) <= 128:
        raise AuthenticationError("a valid API key is required")

    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    matched_tenant: str | None = None
    for expected_digest, tenant_id in settings.api_key_credentials.items():
        if hmac.compare_digest(digest, expected_digest.lower()):
            matched_tenant = tenant_id
    if matched_tenant is None:
        raise AuthenticationError("a valid API key is required")
    return AuthenticatedPrincipal(
        tenant_id=matched_tenant,
        actor_id=f"api-key:{digest[:12]}",
    )
