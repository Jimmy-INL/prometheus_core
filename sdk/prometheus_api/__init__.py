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

"""Prometheus API - Unified package for storage client and agent utilities."""

from importlib.metadata import PackageNotFoundError, version

from .prompts import load_prompt

try:
    __version__ = version("prometheus-api")
except PackageNotFoundError:
    # Running from a plain source checkout (e.g. sys.path injection in tests)
    # without an installed distribution.
    __version__ = "0.0.0+unknown"

__all__ = ["__version__", "load_prompt"]
