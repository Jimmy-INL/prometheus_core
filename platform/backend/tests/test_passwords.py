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

"""Unit tests for app.passwords -- bcrypt hashing for local accounts."""

from __future__ import annotations

from app.passwords import hash_password, verify_password


def test_hash_is_not_plaintext():
    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert hashed.startswith("$2b$")  # bcrypt hash prefix


def test_verify_correct_password():
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", hashed) is True


def test_verify_wrong_password():
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("wrong-password", hashed) is False


def test_verify_malformed_hash_returns_false_not_raise():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_verify_empty_hash_returns_false_not_raise():
    assert verify_password("anything", "") is False


def test_two_hashes_of_same_password_differ():
    """bcrypt salts each hash -- two calls must not produce identical output."""
    h1 = hash_password("same-password")
    h2 = hash_password("same-password")
    assert h1 != h2
    assert verify_password("same-password", h1) is True
    assert verify_password("same-password", h2) is True
