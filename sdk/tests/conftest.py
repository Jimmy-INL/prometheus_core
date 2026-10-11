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

"""Pytest configuration for prometheus_api tests."""

import pytest


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests in test_integration.py with the integration marker."""
    for item in items:
        if "test_integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def _disable_identity_for_legacy_tests(request, monkeypatch):
    """Default all tests to USER_IDENTITY_REQUIRED=false.

    Tests in test_identity.py supply their own identity env vars via an
    autouse fixture that takes precedence over this one (last-writer wins for
    monkeypatch within the same scope).  All other tests pre-date identity and
    test agent mechanics without attaching a userToken — this fixture keeps
    them passing by defaulting to non-required mode.
    """
    # Skip if the test's own module already sets USER_IDENTITY_REQUIRED.
    if "test_identity" not in str(request.fspath):
        monkeypatch.setenv("USER_IDENTITY_REQUIRED", "false")
