"""Shared test setup for the client-agent suite.

Makes the client-agent modules and the canonical wire contract
(prometheus_api.contract) importable. The contract is pre-imported here so
that test files which stub the heavy prometheus_api.agent runtime in
sys.modules do not shadow it (sys.modules hits short-circuit later imports).
"""

import sys
from pathlib import Path

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

def _import_light_modules() -> None:
    # The dependency-light prometheus_api modules the client-agent imports at
    # module level (the heavy agent runtime is stubbed by individual tests).
    import prometheus_api.a2a_stream  # noqa: F401
    import prometheus_api.contract  # noqa: F401
    import prometheus_api.llm_client  # noqa: F401
    import prometheus_api.redis_utils  # noqa: F401


try:
    _import_light_modules()
except ImportError:
    # Convenience fallback for a side-by-side checkout of prometheus_api.
    # These modules need only pydantic/httpx/redis, so this works without the
    # agent runtime (a2a-sdk, litellm) installed.
    _SIBLING = Path(__file__).resolve().parents[4] / "prometheus_api"
    if _SIBLING.is_dir():
        sys.path.insert(0, str(_SIBLING))
    try:
        _import_light_modules()
    except ImportError as exc:  # no sibling checkout either — tell the dev what to do
        raise ImportError(
            "client-agent tests need the prometheus_api package. Install it "
            "into your test environment:\n"
            "  uv pip install git+https://github.inl.gov/genesis/prometheus_api.git\n"
            "or clone prometheus_api next to this repository."
        ) from exc


def _stub_langchain_if_missing() -> None:
    """Install a minimal StructuredTool stub when langchain-core is absent."""
    import types

    try:
        import langchain_core.tools  # noqa: F401
    except ImportError:
        langchain_core = sys.modules.setdefault("langchain_core", types.ModuleType("langchain_core"))
        tools_module = types.ModuleType("langchain_core.tools")

        class _StructuredTool:
            """Functional stub: preserves name/func so planner tools stay testable."""

            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

            @classmethod
            def from_function(cls, func=None, coroutine=None, name="", description="", **kwargs):
                return cls(
                    func=func, coroutine=coroutine, name=name, description=description, **kwargs
                )

        tools_module.StructuredTool = _StructuredTool
        sys.modules["langchain_core.tools"] = tools_module
        langchain_core.tools = tools_module


_stub_langchain_if_missing()
