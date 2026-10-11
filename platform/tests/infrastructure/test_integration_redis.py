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

"""Integration tests for the Valkey Redis-compatible container."""

import subprocess

import pytest
import redis as redis_lib


pytestmark = pytest.mark.integration


@pytest.fixture
def redis_client(docker_compose_up, env_test_file):
    """Create a Redis client connected to the test Valkey instance."""
    # Read password from .env.test
    env_vars = {}
    for line in env_test_file.read_text().splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            env_vars[k] = v

    port = int(env_vars.get("REDIS_LOCAL_PORT", "16379"))
    password = env_vars.get("REDIS_PASSWORD", "")

    client = redis_lib.Redis(host="localhost", port=port, password=password, decode_responses=True)
    yield client
    client.close()


def test_valkey_container_running(docker_compose_up):
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Status}}", "agent-valkey"],
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "running"


def test_valkey_accepts_authenticated_connection(redis_client):
    assert redis_client.ping() is True


def test_valkey_rejects_unauthenticated_connection(docker_compose_up, env_test_file):
    """Connecting without a password should raise an authentication error."""
    env_vars = {}
    for line in env_test_file.read_text().splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            env_vars[k] = v

    port = int(env_vars.get("REDIS_LOCAL_PORT", "16379"))

    client = redis_lib.Redis(host="localhost", port=port, decode_responses=True)
    try:
        with pytest.raises(redis_lib.exceptions.AuthenticationError):
            client.ping()
    finally:
        client.close()


def test_valkey_set_get(redis_client):
    """SET and GET round-trip should work."""
    test_key = "__infra_test_key__"
    try:
        redis_client.set(test_key, "test_value")
        assert redis_client.get(test_key) == "test_value"
    finally:
        redis_client.delete(test_key)


def test_valkey_appendonly_enabled(redis_client):
    config = redis_client.config_get("appendonly")
    assert config.get("appendonly") == "yes"
