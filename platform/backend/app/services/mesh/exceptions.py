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

"""Exceptions for the mesh converter library.

Ported verbatim from the old ``frontend/components/exodus/exceptions.py`` (minus the
unused ``FileNotFoundError`` subclass, which shadowed the builtin and was never
raised — the pipeline raises :class:`InvalidExodusFileError` for a missing file).
"""


class ConverterError(Exception):
    """Base exception for converter errors."""


class InvalidExodusFileError(ConverterError):
    """Raised when the file is not a valid Exodus II file (or cannot be read)."""


class ConversionError(ConverterError):
    """Raised when conversion fails."""


class UnsupportedFeatureError(ConverterError):
    """Raised when a requested feature is not supported."""
