"""ORM models for the admin plane: local + auto-provisioned OIDC users, OIDC
provider configuration, and RS256 signing keys.

Alembic migrations under ``backend/alembic/`` are generated from these models
and are the source of truth for the deployed schema; tests instead call
``app.db.create_all_for_tests()`` against an in-memory SQLite engine and skip
Alembic entirely (see ``tests/conftest.py``).

Secrets at rest: ``OidcProvider.client_secret_encrypted`` and
``SigningKey.private_key_encrypted`` are Fernet-encrypted blobs (see
``app/crypto.py``) -- the plaintext never round-trips through these column
names; encrypt/decrypt at the call site, not in the model.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, LargeBinary, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    # Uuid (not the Postgres-specific dialect type) so the same model works
    # against both admin-db (Postgres, production) and the in-memory SQLite
    # engine tests use (see app/db.py::create_all_for_tests, tests/conftest.py).
    return mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)


class User(Base):
    """A platform account -- created locally by an admin, via the first-run
    setup wizard, or auto-provisioned on a successful OIDC login.

    Local accounts: ``provider="credentials"``, ``password_hash`` set,
    ``external_subject`` NULL. OIDC accounts: ``provider`` is the owning
    ``OidcProvider.provider_id``, ``password_hash`` NULL, ``external_subject``
    is the IdP's ``sub`` claim. The unique constraint on
    ``(provider, external_subject)`` is what makes OIDC login idempotent --
    a returning user resolves to the same row every time.
    """

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("provider", "external_subject", name="uq_users_provider_subject"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    provider: Mapped[str] = mapped_column(String(255), nullable=False, default="credentials")
    external_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OidcProvider(Base):
    """Admin-configured generic-OIDC identity provider.

    ``provider_id`` is the URL slug used in ``GET /api/auth/login/{provider_id}``
    and ``GET /api/auth/callback/{provider_id}``, and is what gets stored in
    ``User.provider`` for accounts created through this provider. Renaming it
    after users exist would orphan their ``User.provider`` value -- the admin
    UI should treat it as immutable after creation.
    """

    __tablename__ = "oidc_providers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    provider_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer_url: Mapped[str] = mapped_column(String(512), nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    client_secret_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    scopes: Mapped[str] = mapped_column(String(512), nullable=False, default="openid profile email")
    default_role: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SigningKey(Base):
    """An RS256 keypair for the multi-user identity plane (see
    ``prometheus_api.agent.identity`` and ``app/identity.py``).

    At most one row has ``is_active=True`` at a time -- that is the key
    ``mint_for_user`` signs new tokens with. Retired keys (``retired_at`` set)
    stay in the table and keep appearing in ``GET /.well-known/jwks.json``
    until an admin decides they're safe to delete, so tokens minted before a
    rotation remain verifiable until they naturally expire.
    """

    __tablename__ = "signing_keys"

    id: Mapped[uuid.UUID] = _uuid_pk()
    kid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    private_key_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    public_key_pem: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
