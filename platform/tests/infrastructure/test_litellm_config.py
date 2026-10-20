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

"""Validate litellm_config.yaml structure and settings."""


def test_litellm_config_is_valid_yaml(litellm_config_data):
    assert isinstance(litellm_config_data, dict)


def test_litellm_config_has_model_list(litellm_config_data):
    assert "model_list" in litellm_config_data


def test_litellm_config_defines_medium_alias(litellm_config_data):
    models = {entry.get("model_name"): entry.get("litellm_params", {}) for entry in litellm_config_data["model_list"]}
    assert models["medium"]["model"] == "anthropic/claude-sonnet-5-5"
    assert models["medium"]["api_key"] == "os.environ/LLM_API_KEY"


def test_litellm_config_has_general_settings(litellm_config_data):
    assert "general_settings" in litellm_config_data


def test_master_key_reads_from_env(litellm_config_data):
    settings = litellm_config_data["general_settings"]
    assert settings.get("master_key") == "os.environ/LITELLM_MASTER_KEY"


def test_database_url_reads_from_env(litellm_config_data):
    settings = litellm_config_data["general_settings"]
    assert settings.get("database_url") == "os.environ/DATABASE_URL"


def test_store_model_in_db_enabled(litellm_config_data):
    settings = litellm_config_data["general_settings"]
    assert settings.get("store_model_in_db") is True
