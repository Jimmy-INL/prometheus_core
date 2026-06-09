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

try:
    import prometheus_api.contract  # noqa: F401
except ImportError:
    # Monorepo layout: fall back to the sibling prometheus_api checkout.
    # prometheus_api.contract is dependency-light (pydantic only), so this
    # works without the agent runtime (a2a-sdk, litellm) installed.
    _SIBLING = Path(__file__).resolve().parents[4] / "prometheus_api"
    sys.path.insert(0, str(_SIBLING))
    import prometheus_api.contract  # noqa: F401
