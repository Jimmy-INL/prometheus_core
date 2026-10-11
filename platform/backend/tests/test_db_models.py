# This file is part of Prometheus
# https://inl.gov/super-intelligence/prometheus/
#
# Copyright 2026 Battelle Energy Alliance, LLC
# All rights reserved, see NOTICE.txt for full restrictions
# https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt
#
# Licensed under the MIT License, please see LICENSE for details
# https://github.com/idaholab/prometheus_core/blob/main/LICENSE
#
# SPDX-License-Identifier: MIT

"""Unit tests for the admin-plane ORM models (app/db/models.py).

Uses the ``db_session`` fixture (in-memory SQLite, schema from
Base.metadata -- see tests/conftest.py). Exercises the ORM layer directly,
not through any router yet.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import OidcProvider, SigningKey, User


@pytest.mark.asyncio
async def test_create_local_user_round_trips(db_session):
    user = User(username="alice", password_hash="hashed", role="admin", provider="credentials")
    db_session.add(user)
    await db_session.commit()

    fetched = await db_session.scalar(select(User).where(User.username == "alice"))
    assert fetched is not None
    assert fetched.role == "admin"
    assert fetched.is_active is True  # default
    assert fetched.external_subject is None


@pytest.mark.asyncio
async def test_username_must_be_unique(db_session):
    db_session.add(User(username="bob", provider="credentials"))
    await db_session.commit()

    db_session.add(User(username="bob", provider="credentials"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_provider_and_external_subject_unique_together(db_session):
    """Two different OIDC providers can each have a user with the same
    external_subject -- the uniqueness is per (provider, external_subject)."""
    db_session.add(User(username="okta-user1", provider="okta", external_subject="sub-123"))
    db_session.add(User(username="google-user1", provider="google", external_subject="sub-123"))
    await db_session.commit()  # must not raise

    count = len((await db_session.execute(select(User))).all())
    assert count == 2


@pytest.mark.asyncio
async def test_duplicate_provider_subject_pair_rejected(db_session):
    db_session.add(User(username="u1", provider="okta", external_subject="sub-456"))
    await db_session.commit()

    db_session.add(User(username="u2", provider="okta", external_subject="sub-456"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_create_oidc_provider(db_session):
    provider = OidcProvider(
        provider_id="okta",
        display_name="Okta",
        issuer_url="https://example.okta.com",
        client_id="client-abc",
        client_secret_encrypted=b"encrypted-bytes",
        default_role="user",
    )
    db_session.add(provider)
    await db_session.commit()

    fetched = await db_session.scalar(select(OidcProvider).where(OidcProvider.provider_id == "okta"))
    assert fetched is not None
    assert fetched.is_enabled is True  # default
    assert fetched.scopes == "openid profile email"  # default


@pytest.mark.asyncio
async def test_provider_id_must_be_unique(db_session):
    def _make(client_id: str) -> OidcProvider:
        return OidcProvider(
            provider_id="dup",
            display_name="Dup",
            issuer_url="https://example.com",
            client_id=client_id,
            client_secret_encrypted=b"x",
        )

    db_session.add(_make("a"))
    await db_session.commit()

    db_session.add(_make("b"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_create_signing_key(db_session):
    key = SigningKey(
        kid="kid-1",
        private_key_encrypted=b"encrypted-private-key",
        public_key_pem="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----",
    )
    db_session.add(key)
    await db_session.commit()

    fetched = await db_session.scalar(select(SigningKey).where(SigningKey.kid == "kid-1"))
    assert fetched is not None
    assert fetched.is_active is False  # default -- must be explicitly activated
    assert fetched.retired_at is None


@pytest.mark.asyncio
async def test_kid_must_be_unique(db_session):
    db_session.add(SigningKey(kid="same-kid", private_key_encrypted=b"a", public_key_pem="pem-a"))
    await db_session.commit()

    db_session.add(SigningKey(kid="same-kid", private_key_encrypted=b"b", public_key_pem="pem-b"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_ids_are_distinct_uuids(db_session):
    u1 = User(username="u1", provider="credentials")
    u2 = User(username="u2", provider="credentials")
    db_session.add_all([u1, u2])
    await db_session.commit()

    assert isinstance(u1.id, uuid.UUID)
    assert u1.id != u2.id
