"""Prometheus API - Unified package for storage client and agent utilities."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("prometheus-api")
except PackageNotFoundError:
    # Running from a plain source checkout (e.g. sys.path injection in tests)
    # without an installed distribution.
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
