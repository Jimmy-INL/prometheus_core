"""
Plant Requirements Agent - A2A Agent for Nuclear System Design & Requirements

Wraps the nucsys_agent package in the Prometheus A2A protocol.

Exposes six skills via an 'action' routing parameter:
  1. design                   - One-shot nuclear system loop design
  2. design_chat              - Stateless conversational design step
  3. requirements             - One-shot component requirements
  4. requirements_chat        - Stateless conversational requirements step
  5. requirements_from_design - Requirements seeded from a sized design node
  6. audit                    - Engineering model audit Q&A
"""

import sys
import logging
import asyncio
from typing import Dict, Any
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from prometheus_api.agent import (
    PrometheusAgent,
    RequestContext,
    EventQueue,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

# Add shared directory to path so nucsys_agent package is importable
sys.path.insert(0, "/app")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Thread pool for running synchronous nucsys_agent calls
_EXECUTOR = ThreadPoolExecutor(max_workers=4)


class PlantRequirementsAgent(PrometheusAgent):
    """
    Plant Requirements Agent.

    Provides nuclear system design, component requirements generation,
    and engineering model audit capabilities via the A2A protocol.

    Supported actions (pass as 'action' in the message JSON):
      - design                   : one-shot loop design from natural language
      - design_chat              : stateless multi-turn loop design
      - requirements             : one-shot component requirements filtering
      - requirements_chat        : stateless multi-turn requirements conversation
      - requirements_from_design : requirements pre-seeded from a loop design node
      - audit                    : ask questions about engineering models
    """

    async def _execute(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """
        Route incoming A2A request to the appropriate nucsys_agent capability.

        The message text must be a JSON object with an 'action' field that
        selects the skill, plus any skill-specific parameters.

        Args:
            params: Parameters extracted from the A2A message JSON
            context: A2A request context (task_id, context_id)
            event_queue: Queue for sending progress updates

        Returns:
            Dict with 'status' ('success'|'error') plus skill-specific fields
        """
        action = params.get("action")
        if not action:
            raise ValueError(
                "Parameter 'action' is required. Valid actions: "
                "design, design_chat, requirements, requirements_chat, "
                "requirements_from_design, audit"
            )

        # Send initial working status update
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                final=False,
                status=TaskStatus(state=TaskState.working),
            )
        )

        loop = asyncio.get_event_loop()

        dispatch = {
            "design": self._handle_design,
            "design_chat": self._handle_design_chat,
            "requirements": self._handle_requirements,
            "requirements_chat": self._handle_requirements_chat,
            "requirements_from_design": self._handle_requirements_from_design,
            "audit": self._handle_audit,
        }

        handler = dispatch.get(action)
        if handler is None:
            raise ValueError(
                f"Unknown action: '{action}'. Valid actions: "
                + ", ".join(dispatch.keys())
            )

        logger.info("Processing action='%s' task_id=%s", action, context.task_id)
        result = await loop.run_in_executor(_EXECUTOR, handler, params)

        result["agent"] = "Plant Requirements Agent"
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        return result

    # ------------------------------------------------------------------
    # Skill handlers (synchronous — run in thread executor)
    # ------------------------------------------------------------------

    def _handle_design(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        One-shot nuclear system loop design from a natural language query.

        Required params:
          query (str): e.g. "300 MWth PWR primary loop"

        Returns:
          spec, alchemy_db, validation_issues, export_issues
        """
        from nucsys_agent.workflow import run_agent
        from nucsys_agent.exceptions import AgentError

        query = params.get("query")
        if not query:
            raise ValueError("'query' is required for action 'design'")

        try:
            res = run_agent(query)
        except AgentError as e:
            return {"status": "error", "error": str(e)}

        return {
            "status": "success",
            "spec": res.spec.model_dump(),
            "validation_issues": [i.__dict__ for i in res.validation_issues],
            "export_issues": [i.__dict__ for i in res.export_issues],
            "alchemy_db": res.alchemy_db,
        }

    def _handle_design_chat(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stateless multi-turn loop design conversation.

        The client maintains the full message history and sends it each turn.
        On the first turn, 'history' is empty (or omitted). Subsequent turns
        include all prior messages so the agent can reconstruct state.

        Required params:
          initial_query (str): The initial design query

        Optional params:
          history (list[{role, content}]): Full message history; empty for first turn

        Returns:
          agent_reply, phase, is_done; on completion also spec, alchemy_db,
          validation_issues, export_issues
        """
        from nucsys_agent.conversation import (
            ChatMessage,
            start_conversation,
            advance_conversation,
            replay_history,
        )

        initial_query = params.get("initial_query")
        if not initial_query:
            raise ValueError("'initial_query' is required for action 'design_chat'")

        history_raw = params.get("history", [])

        if not history_raw:
            turn = start_conversation(initial_query)
        else:
            msgs = [ChatMessage(role=m["role"], content=m["content"]) for m in history_raw]
            state = replay_history(msgs, initial_query)
            last_user = next(
                (m["content"] for m in reversed(history_raw) if m["role"] == "user"), ""
            )
            turn = advance_conversation(state, last_user, initial_query)

        resp: Dict[str, Any] = {
            "status": "success",
            "agent_reply": turn.agent_reply,
            "phase": turn.state.phase,
            "is_done": turn.is_done,
            "error": turn.error,
        }
        if turn.is_done and turn.result is not None:
            resp["spec"] = turn.result.spec.model_dump()
            resp["alchemy_db"] = turn.result.alchemy_db
            resp["validation_issues"] = [i.__dict__ for i in turn.result.validation_issues]
            resp["export_issues"] = [i.__dict__ for i in turn.result.export_issues]
        return resp

    def _handle_requirements(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        One-shot component requirements filtering.

        Provide a component type and its full profile to receive applicable
        requirements from the ~1500-requirement baseline.

        Required params:
          component_type (str): pump | valve | condenser | steam_generator |
                                pressurizer | turbine
          profile (dict):       component profile with classification and sizing fields

        Returns:
          applicable_requirements, tbd_requirements, validation summary
        """
        from nucsys_agent.requirements.loader import resolve_component, load_baseline
        from nucsys_agent.requirements.filter import filter_requirements

        component_type = params.get("component_type")
        profile = params.get("profile")
        if not component_type:
            raise ValueError("'component_type' is required for action 'requirements'")
        if profile is None:
            raise ValueError("'profile' is required for action 'requirements'")

        key = resolve_component(component_type)
        if key is None:
            raise ValueError(
                f"Unknown component type '{component_type}'. "
                "Valid types: pump, valve, condenser, steam_generator, pressurizer, turbine."
            )

        baseline = load_baseline(key)
        result = filter_requirements(baseline, profile, key)
        return {"status": "success", **result}

    def _handle_requirements_chat(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stateless multi-turn requirements conversation.

        The agent asks clarifying questions to gather the component profile,
        then returns the filtered requirements instance when complete.

        Required params:
          initial_query (str): e.g. "requirements for a PWR feedwater pump"

        Optional params:
          history (list[{role, content}]): Full message history; empty for first turn

        Returns:
          agent_reply, phase, is_done; on completion also requirements_instance
        """
        from nucsys_agent.requirements.conversation import (
            ReqChatMessage,
            start_req_conversation,
            advance_req_conversation,
            replay_req_history,
        )

        initial_query = params.get("initial_query")
        if not initial_query:
            raise ValueError("'initial_query' is required for action 'requirements_chat'")

        history_raw = params.get("history", [])

        if not history_raw:
            turn = start_req_conversation(initial_query)
        else:
            msgs = [ReqChatMessage(role=m["role"], content=m["content"]) for m in history_raw]
            state = replay_req_history(msgs, initial_query)
            last_user = next(
                (m["content"] for m in reversed(history_raw) if m["role"] == "user"), ""
            )
            turn = advance_req_conversation(state, last_user, initial_query)

        resp: Dict[str, Any] = {
            "status": "success",
            "agent_reply": turn.agent_reply,
            "phase": turn.state.phase,
            "is_done": turn.is_done,
            "error": turn.error,
        }
        if turn.is_done and turn.result_json is not None:
            resp["requirements_instance"] = turn.result_json
        return resp

    def _handle_requirements_from_design(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stateless requirements conversation seeded from a loop-design node.

        Numeric optional fields (flow rate, head, rated power, thermal duty,
        operating pressures) are automatically extracted from the sized node
        properties. Only classification fields are asked interactively.

        Typical flow:
          1. Call action='design' → receive alchemy_db
          2. Pick a node (e.g. "Primary Sink", "SG", "Turbine", "FWP")
          3. Send its properties as node_props with empty history (first turn)
          4. Repeat with growing history until is_done is true

        Required params:
          node_name  (str):  Node name from alchemy_db (e.g. "Primary Sink")
          node_props (dict): Properties dict of the node from alchemy_db

        Optional params:
          all_node_props (dict | null): Properties for all nodes (context)
          history (list[{role, content}]): Full message history; empty for first turn

        Returns:
          agent_reply, phase, is_done; on completion also requirements_instance
        """
        from nucsys_agent.requirements.bridge import extract_design_numerics
        from nucsys_agent.requirements.conversation import (
            ReqChatMessage,
            start_req_conversation_from_design,
            advance_req_conversation_from_design,
            replay_req_history_from_design,
        )

        node_name = params.get("node_name")
        node_props = params.get("node_props")
        if not node_name:
            raise ValueError("'node_name' is required for action 'requirements_from_design'")
        if node_props is None:
            raise ValueError("'node_props' is required for action 'requirements_from_design'")

        all_node_props = params.get("all_node_props")
        history_raw = params.get("history", [])

        if not history_raw:
            turn = start_req_conversation_from_design(node_name, node_props, all_node_props)
        else:
            component_key, prefilled_numeric = extract_design_numerics(
                node_name, node_props, all_node_props
            )
            if component_key is None:
                raise ValueError(
                    f"Node '{node_name}' has no requirements mapping. "
                    "Supported nodes: Primary Sink (pump), SG (steam_generator), "
                    "Turbine, FWP (pump)."
                )
            msgs = [ReqChatMessage(role=m["role"], content=m["content"]) for m in history_raw]
            state = replay_req_history_from_design(msgs, component_key, prefilled_numeric)
            last_user = next(
                (m["content"] for m in reversed(history_raw) if m["role"] == "user"), ""
            )
            turn = advance_req_conversation_from_design(state, last_user)

        resp: Dict[str, Any] = {
            "status": "success",
            "agent_reply": turn.agent_reply,
            "phase": turn.state.phase,
            "is_done": turn.is_done,
            "error": turn.error,
        }
        if turn.is_done and turn.result_json is not None:
            resp["requirements_instance"] = turn.result_json
        return resp

    def _handle_audit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Answer questions about the engineering models in nucsys_agent.

        Use question='list' to get a catalogue of available topics.
        Set topic_id to retrieve a specific topic directly.

        Required params (one of):
          question (str): Free-text question about engineering models
          topic_id (str): Specific topic ID from a previous matched_topics list

        Returns:
          answer, matched_topics, available_topics
        """
        from nucsys_agent.audit import AuditEngine, TOPICS
        from nucsys_agent.audit.engine import _score_topic, _tokenise, _MIN_SCORE

        question = params.get("question")
        topic_id = params.get("topic_id")

        engine = AuditEngine()
        available = engine.topic_ids()

        # Direct topic lookup by ID
        if topic_id:
            body = engine.get_topic(topic_id)
            if body is None:
                raise ValueError(
                    f"Topic '{topic_id}' not found. Available: {', '.join(available)}"
                )
            return {
                "status": "success",
                "answer": body,
                "matched_topics": [topic_id],
                "available_topics": available,
            }

        if not question:
            raise ValueError(
                "'question' is required for action 'audit' (or provide 'topic_id')"
            )

        answer = engine.ask(question)

        # Re-score to find which topics contributed
        q_lower = question.lower()
        tokens = _tokenise(q_lower)
        matched = [
            t["id"] for t in TOPICS
            if _score_topic(q_lower, tokens, t) >= _MIN_SCORE
        ]

        return {
            "status": "success",
            "answer": answer,
            "matched_topics": matched,
            "available_topics": available,
        }


if __name__ == "__main__":
    agent = PlantRequirementsAgent(agent_name="Plant Requirements Agent")
    agent.run()
