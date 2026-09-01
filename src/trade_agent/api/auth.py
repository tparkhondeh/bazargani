from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from trade_agent.config import ALLOWED_API_KEY_ROLES, Settings


class AuthenticationError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    tenant_id: str
    actor_id: str
    roles: frozenset[str]


def authenticate_api_key(settings: Settings, api_key: str | None) -> AuthenticatedPrincipal:
    if not settings.auth_enabled:
        return AuthenticatedPrincipal(
            tenant_id="local-development",
            actor_id="development-auth-disabled",
            roles=ALLOWED_API_KEY_ROLES,
        )
    if api_key is None or not 32 <= len(api_key) <= 128:
        raise AuthenticationError("a valid API key is required")

    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    matched_tenant: str | None = None
    matched_digest: str | None = None
    for expected_digest, tenant_id in settings.api_key_credentials.items():
        if hmac.compare_digest(digest, expected_digest.lower()):
            matched_tenant = tenant_id
            matched_digest = expected_digest.lower()
    if matched_tenant is None:
        raise AuthenticationError("a valid API key is required")
    return AuthenticatedPrincipal(
        tenant_id=matched_tenant,
        actor_id=f"api-key:{digest[:12]}",
        roles=frozenset(settings.api_key_roles.get(matched_digest or "", ())),
    )


def authorize_role(principal: AuthenticatedPrincipal, role: str) -> None:
    if role not in ALLOWED_API_KEY_ROLES or role not in principal.roles:
        raise AuthorizationError("the credential is not authorized for this operation")
