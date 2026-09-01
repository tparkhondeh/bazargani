import hashlib
import unittest

from pydantic import ValidationError

from trade_agent.api.auth import (
    AuthenticationError,
    AuthorizationError,
    authenticate_api_key,
    authorize_role,
)
from trade_agent.config import Settings


class AuthenticationTests(unittest.TestCase):
    def test_valid_key_resolves_tenant_without_exposing_the_secret(self) -> None:
        key = "valid-test-api-key-00000000000001"
        digest = hashlib.sha256(key.encode()).hexdigest()
        settings = Settings(
            environment="test",
            auth_enabled=True,
            api_key_credentials={digest: "tenant-a"},
            api_key_roles={digest.upper(): ["RESEARCH_REVIEWER", "RESEARCH_REVIEWER"]},
        )

        principal = authenticate_api_key(settings, key)

        self.assertEqual(principal.tenant_id, "tenant-a")
        self.assertEqual(principal.actor_id, f"api-key:{digest[:12]}")
        self.assertEqual(principal.roles, frozenset({"RESEARCH_REVIEWER"}))
        self.assertNotIn(key, principal.actor_id)
        authorize_role(principal, "RESEARCH_REVIEWER")
        with self.assertRaises(AuthorizationError):
            authorize_role(principal, "SUPPLIER_IDENTITY_REVIEWER")
        with self.assertRaises(AuthorizationError):
            authorize_role(principal, "ADMIN")

    def test_invalid_key_is_rejected(self) -> None:
        key = "valid-test-api-key-00000000000001"
        settings = Settings(
            environment="test",
            auth_enabled=True,
            api_key_credentials={hashlib.sha256(key.encode()).hexdigest(): "tenant-a"},
        )

        with self.assertRaises(AuthenticationError):
            authenticate_api_key(settings, "invalid-test-api-key-000000000000")

    def test_development_can_explicitly_disable_authentication(self) -> None:
        principal = authenticate_api_key(Settings(environment="development"), None)

        self.assertEqual(principal.tenant_id, "local-development")
        self.assertEqual(principal.actor_id, "development-auth-disabled")
        authorize_role(principal, "RESEARCH_REVIEWER")
        authorize_role(principal, "SUPPLIER_IDENTITY_REVIEWER")

    def test_production_fails_closed_without_authentication(self) -> None:
        with self.assertRaisesRegex(ValidationError, "production requires authentication"):
            Settings(
                environment="production",
                database_url="postgresql+psycopg://app:secret@db/app",
                auto_create_schema=False,
            )

    def test_production_provider_requires_explicit_terms_approval(self) -> None:
        digest = hashlib.sha256(b"production-api-key-fixture").hexdigest()
        common = {
            "environment": "production",
            "database_url": "postgresql+psycopg://app:secret@db/app",
            "auto_create_schema": False,
            "auth_enabled": True,
            "api_key_credentials": {digest: "tenant-a"},
        }

        with self.assertRaisesRegex(ValidationError, "explicit terms approval"):
            Settings(**common)

        enabled = Settings(**common, ecb_terms_approved=True)
        disabled = Settings(**common, ecb_enabled=False)
        self.assertTrue(enabled.ecb_enabled)
        self.assertTrue(enabled.ecb_terms_approved)
        self.assertFalse(disabled.ecb_enabled)
        self.assertFalse(disabled.ecb_terms_approved)

    def test_authentication_requires_well_formed_hashed_credentials(self) -> None:
        with self.assertRaisesRegex(ValidationError, "SHA-256"):
            Settings(
                environment="test",
                auth_enabled=True,
                api_key_credentials={"plain-text-key": "tenant-a"},
            )

    def test_role_configuration_fails_closed_for_orphans_and_unknown_roles(self) -> None:
        key_digest = hashlib.sha256(b"configured-key").hexdigest()
        orphan_digest = hashlib.sha256(b"orphan-key").hexdigest()

        with self.assertRaisesRegex(ValidationError, "credential identifiers must be unique"):
            Settings(
                environment="test",
                auth_enabled=True,
                api_key_credentials={
                    key_digest: "tenant-a",
                    key_digest.upper(): "tenant-a",
                },
            )
        with self.assertRaisesRegex(ValidationError, "role identifiers must be SHA-256"):
            Settings(
                environment="test",
                auth_enabled=True,
                api_key_credentials={key_digest: "tenant-a"},
                api_key_roles={"not-a-digest": ["RESEARCH_REVIEWER"]},
            )
        with self.assertRaisesRegex(ValidationError, "configured credential"):
            Settings(
                environment="test",
                auth_enabled=True,
                api_key_credentials={key_digest: "tenant-a"},
                api_key_roles={orphan_digest: ["RESEARCH_REVIEWER"]},
            )
        with self.assertRaisesRegex(ValidationError, "unsupported values"):
            Settings(
                environment="test",
                auth_enabled=True,
                api_key_credentials={key_digest: "tenant-a"},
                api_key_roles={key_digest: ["ADMIN"]},
            )
        with self.assertRaisesRegex(ValidationError, "cannot be empty"):
            Settings(
                environment="test",
                auth_enabled=True,
                api_key_credentials={key_digest: "tenant-a"},
                api_key_roles={key_digest: []},
            )
        with self.assertRaisesRegex(ValidationError, "role identifiers must be unique"):
            Settings(
                environment="test",
                auth_enabled=True,
                api_key_credentials={key_digest: "tenant-a"},
                api_key_roles={
                    key_digest: ["RESEARCH_REVIEWER"],
                    key_digest.upper(): ["SUPPLIER_IDENTITY_REVIEWER"],
                },
            )


if __name__ == "__main__":
    unittest.main()
