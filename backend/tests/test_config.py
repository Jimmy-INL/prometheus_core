"""Config + startup guards.

Covers DEP-1 (fold ``REDIS_PASSWORD`` into a credential-less ``REDIS_URL``) and
BLK-3 (the lifespan refuses to start without a JWT signing secret).
"""

import asyncio

import pytest

from app import config as config_mod
from app.config import settings
from app.main import app, lifespan


# --------------------------------------------------------------------------- #
# DEP-1 — REDIS_PASSWORD folding
# --------------------------------------------------------------------------- #


def test_redis_url_folds_password_when_url_has_no_userinfo(monkeypatch):
    monkeypatch.setenv("REDIS_PASSWORD", "s3cr3t")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379")
    assert config_mod._redis_url({}) == "redis://:s3cr3t@redis:6379"


def test_redis_url_noop_when_url_already_has_credentials(monkeypatch):
    # The documented .env.example form embeds the password in the URL — untouched.
    monkeypatch.setenv("REDIS_PASSWORD", "s3cr3t")
    monkeypatch.setenv("REDIS_URL", "redis://:existing@redis:6379")
    assert config_mod._redis_url({}) == "redis://:existing@redis:6379"


def test_redis_url_noop_when_no_password(monkeypatch):
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379")
    assert config_mod._redis_url({}) == "redis://redis:6379"


def test_redis_url_url_encodes_special_chars(monkeypatch):
    monkeypatch.setenv("REDIS_PASSWORD", "p@ss/w:rd")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379")
    assert config_mod._redis_url({}) == "redis://:p%40ss%2Fw%3Ard@redis:6379"


# --------------------------------------------------------------------------- #
# BLK-3 — lifespan requires a signing secret
# --------------------------------------------------------------------------- #


def test_lifespan_raises_without_jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "", raising=False)

    async def run() -> None:
        async with lifespan(app):
            pass

    with pytest.raises(RuntimeError, match="jwt_secret is not configured"):
        asyncio.run(run())


def test_lifespan_starts_with_jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "x" * 32, raising=False)

    async def run() -> bool:
        async with lifespan(app):
            return True

    assert asyncio.run(run()) is True
