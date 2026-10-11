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

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace


def _load_osti_module():
    repo_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "prometheus_api"))

    module_path = Path(__file__).resolve().parents[1] / "agent.py"
    spec = importlib.util.spec_from_file_location("osti_agent_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_linkify_uses_mapping_for_deduplicated_papers():
    mod = _load_osti_module()

    answers = [
        {"osti_id": "111", "title": "A", "url": "https://osti.gov/biblio/111"},
        {"osti_id": "222", "title": "B", "url": "https://osti.gov/biblio/222"},
        {"osti_id": "111", "title": "A duplicate", "url": "https://osti.gov/biblio/111"},
        {"osti_id": "333", "title": "C", "url": "https://osti.gov/biblio/333"},
    ]
    provenance, paper_to_provenance = mod.deduplicate_provenance_with_mapping(answers)

    text = "Evidence from Paper 1, Paper 3, and Paper 4 supports the conclusion."
    linked = mod.linkify_paper_references(text, provenance, paper_to_provenance)

    assert "[Paper 1](https://osti.gov/biblio/111)" in linked
    assert "[Paper 3](https://osti.gov/biblio/333)" in linked
    assert linked.count("[Paper 1](https://osti.gov/biblio/111)") == 2
    assert "Paper 4" not in linked


def test_linkify_without_mapping_uses_direct_index():
    mod = _load_osti_module()

    provenance = [
        {"source": "OSTI #10", "url": "https://osti.gov/biblio/10"},
        {"source": "OSTI #20", "url": "https://osti.gov/biblio/20"},
    ]
    text = "See Paper 2 for details."
    linked = mod.linkify_paper_references(text, provenance)

    assert linked == "See [Paper 2](https://osti.gov/biblio/20) for details."
    assert "[[2]]" not in linked


def test_memory_answer_sufficient_heuristic_rejects_insufficient_language():
    mod = _load_osti_module()
    text = "There is not enough information in the knowledge base to answer this question reliably."
    assert mod.is_memory_answer_sufficient(text) is False


def test_memory_answer_sufficient_heuristic_accepts_substantive_answer():
    mod = _load_osti_module()
    text = (
        "Based on Fact 1 and Fact 2, SS316 shows improved corrosion resistance between "
        "280C and 320C in high-purity water, with degradation accelerating above 350C."
    )
    assert mod.is_memory_answer_sufficient(text) is True


def test_status_updates_use_a2a_v1_task_states():
    mod = _load_osti_module()
    agent = object.__new__(mod.OSTIResearchAgent)
    sent_statuses = []

    agent._store_status_in_redis = lambda *args, **kwargs: None

    async def capture_status_update(**kwargs):
        sent_statuses.append(kwargs)

    agent.send_status_update = capture_status_update
    context = SimpleNamespace(context_id="context-1")
    event_queue = object()

    asyncio.run(agent._send_status(context, event_queue, "Searching OSTI"))
    asyncio.run(
        agent._send_final_result(
            context,
            event_queue,
            {"status": "completed", "answer": "Research result"},
        )
    )

    assert sent_statuses[0]["state"] == mod.TaskState.TASK_STATE_WORKING
    assert sent_statuses[0]["final"] is False
    assert sent_statuses[1]["state"] == mod.TaskState.TASK_STATE_COMPLETED
    assert sent_statuses[1]["final"] is True
