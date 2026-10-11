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

"""Unit tests for app.crypto -- Fernet encrypt-at-rest for admin-plane secrets."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app import crypto
from app.config import settings


def test_encrypt_then_decrypt_round_trips():
    ciphertext = crypto.encrypt("super-secret-value")
    assert crypto.decrypt(ciphertext) == "super-secret-value"


def test_ciphertext_is_not_plaintext():
    ciphertext = crypto.encrypt("super-secret-value")
    assert b"super-secret-value" not in ciphertext


def test_encrypt_raises_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "admin_db_encryption_key", "")
    with pytest.raises(crypto.EncryptionError, match="ADMIN_DB_ENCRYPTION_KEY"):
        crypto.encrypt("anything")


def test_decrypt_raises_when_unconfigured(monkeypatch):
    ciphertext = crypto.encrypt("value")
    monkeypatch.setattr(settings, "admin_db_encryption_key", "")
    with pytest.raises(crypto.EncryptionError, match="ADMIN_DB_ENCRYPTION_KEY"):
        crypto.decrypt(ciphertext)


def test_encrypt_raises_on_malformed_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_db_encryption_key", "not-a-valid-fernet-key")
    with pytest.raises(crypto.EncryptionError, match="not a valid Fernet key"):
        crypto.encrypt("anything")


def test_decrypt_raises_when_key_rotated(monkeypatch):
    """A value encrypted under one key can't be decrypted under a different one."""
    ciphertext = crypto.encrypt("value")
    monkeypatch.setattr(settings, "admin_db_encryption_key", Fernet.generate_key().decode())
    with pytest.raises(crypto.EncryptionError, match="Could not decrypt"):
        crypto.decrypt(ciphertext)
