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

"""Content-hash caching for converted mesh datasets.

Ported verbatim from the old ``frontend/components/exodus/cache.py``. The dataset id
is ``sha256(file_sha256 : normalized_request_json)[:16]``, so the same mesh + request
always maps to the same cache directory and is converted only once. Pure stdlib — no
VTK import.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def compute_file_hash(file_path: Path, chunk_size: int = 8192) -> str:
    """Compute the SHA-256 hash of a file's contents."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def normalize_request_json(request_dict: dict[str, Any]) -> str:
    """Normalize a request dict to a canonical JSON string.

    Path fields are dropped (they don't affect output content) and ``None`` values
    are removed so equivalent requests hash identically.
    """
    filtered = {k: v for k, v in request_dict.items() if k not in ("input_path", "output_dir") and v is not None}
    return json.dumps(filtered, sort_keys=True, separators=(",", ":"))


def compute_dataset_id(file_path: Path, request_dict: dict[str, Any]) -> str:
    """Derive a stable dataset id from file content + request parameters."""
    file_hash = compute_file_hash(file_path)
    request_json = normalize_request_json(request_dict)
    combined = f"{file_hash}:{request_json}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def get_cache_path(cache_root: Path, dataset_id: str) -> Path:
    """Return the cache directory for a dataset."""
    return cache_root / dataset_id


def is_cached(cache_root: Path, dataset_id: str) -> bool:
    """Whether a dataset has already been converted (its ``manifest.json`` exists)."""
    return (get_cache_path(cache_root, dataset_id) / "manifest.json").exists()
