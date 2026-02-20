"""Caching utilities for converted datasets."""

import hashlib
import json
from pathlib import Path
from typing import Any


def compute_file_hash(file_path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def normalize_request_json(request_dict: dict[str, Any]) -> str:
    """Normalize request dictionary to a canonical JSON string."""
    # Remove path fields as they don't affect output content
    filtered = {k: v for k, v in request_dict.items() if k not in ("input_path", "output_dir") and v is not None}
    return json.dumps(filtered, sort_keys=True, separators=(",", ":"))


def compute_dataset_id(file_path: Path, request_dict: dict[str, Any]) -> str:
    """Compute a unique dataset ID based on file content and request parameters."""
    file_hash = compute_file_hash(file_path)
    request_json = normalize_request_json(request_dict)

    combined = f"{file_hash}:{request_json}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def get_cache_path(cache_root: Path, dataset_id: str) -> Path:
    """Get the cache directory path for a dataset."""
    return cache_root / dataset_id


def is_cached(cache_root: Path, dataset_id: str) -> bool:
    """Check if a dataset is already cached."""
    cache_path = get_cache_path(cache_root, dataset_id)
    manifest_path = cache_path / "manifest.json"
    return manifest_path.exists()
