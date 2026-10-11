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

"""Client Agent - orchestrates specialist agents for engineering requests.

The implementation lives under ``orchestrator/``; this module is the Docker
entry point.
"""
from orchestrator import runtime
from orchestrator.service import OrchestratorAgent

__all__ = ["OrchestratorAgent"]


if __name__ == "__main__":
    agent = OrchestratorAgent()
    agent.run(port=runtime.AGENT_PORT)
