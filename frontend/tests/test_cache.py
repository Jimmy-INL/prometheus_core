"""Tests for components/exodus/cache.py — pure functions, no mocks needed."""

import hashlib
import json
from pathlib import Path

from components.exodus.cache import (
    compute_dataset_id,
    compute_file_hash,
    get_cache_path,
    is_cached,
    normalize_request_json,
)


def test_compute_file_hash(sample_file: Path):
    """Hash a known file and verify SHA-256."""
    expected = hashlib.sha256(b"hello world").hexdigest()
    assert compute_file_hash(sample_file) == expected


def test_compute_file_hash_deterministic(sample_file: Path):
    """Same file produces the same hash on repeated calls."""
    h1 = compute_file_hash(sample_file)
    h2 = compute_file_hash(sample_file)
    assert h1 == h2


def test_normalize_request_json_strips_paths():
    """Path fields (input_path, output_dir) are excluded."""
    req = {"input_path": "/a/b", "output_dir": "/c/d", "representation": "surface"}
    result = normalize_request_json(req)
    parsed = json.loads(result)
    assert "input_path" not in parsed
    assert "output_dir" not in parsed
    assert parsed["representation"] == "surface"


def test_normalize_request_json_removes_none():
    """None values are filtered out."""
    req = {"representation": "surface", "blocks": None, "compress": True}
    result = normalize_request_json(req)
    parsed = json.loads(result)
    assert "blocks" not in parsed
    assert parsed["compress"] is True


def test_normalize_request_json_sorted_keys():
    """Keys are sorted for canonical output."""
    req = {"z_field": 1, "a_field": 2}
    result = normalize_request_json(req)
    assert result == '{"a_field":2,"z_field":1}'


def test_compute_dataset_id_format(sample_file: Path):
    """Dataset ID is a 16-char hex string."""
    did = compute_dataset_id(sample_file, {"representation": "surface"})
    assert len(did) == 16
    assert all(c in "0123456789abcdef" for c in did)


def test_compute_dataset_id_deterministic(sample_file: Path):
    """Same inputs produce the same ID."""
    req = {"representation": "surface"}
    id1 = compute_dataset_id(sample_file, req)
    id2 = compute_dataset_id(sample_file, req)
    assert id1 == id2


def test_compute_dataset_id_varies_with_content(tmp_path: Path):
    """Different file content produces different IDs."""
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("aaa")
    f2.write_text("bbb")
    req = {"representation": "surface"}
    assert compute_dataset_id(f1, req) != compute_dataset_id(f2, req)


def test_get_cache_path():
    """Returns cache_root / dataset_id."""
    root = Path("/tmp/cache")
    assert get_cache_path(root, "abc123") == Path("/tmp/cache/abc123")


def test_is_cached_false(tmp_path: Path):
    """Returns False when no manifest.json exists."""
    assert is_cached(tmp_path, "nonexistent") is False


def test_is_cached_true(tmp_path: Path):
    """Returns True when manifest.json exists in the dataset dir."""
    dataset_dir = tmp_path / "my_dataset"
    dataset_dir.mkdir()
    (dataset_dir / "manifest.json").write_text("{}")
    assert is_cached(tmp_path, "my_dataset") is True
