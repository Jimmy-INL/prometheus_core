"""Tests for the /forget slash command's OSTI knowledge boundary."""

from __future__ import annotations

import asyncio
import fnmatch

from orchestrator import debug_commands, runtime
from orchestrator.models import ConversationRequest


class _FakeRedis:
    def __init__(self, keys: set[str]):
        self.keys = set(keys)

    def scan_iter(self, *, match: str, count: int):
        del count
        return iter(sorted(key for key in self.keys if fnmatch.fnmatch(key, match)))

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.keys:
                self.keys.remove(key)
                deleted += 1
        return deleted


def test_forget_deletes_only_osti_knowledge_facts(monkeypatch) -> None:
    knowledge_keys = {
        "osti:factoid:fact-1",
        "osti:factoid:fact-2",
        "osti:paper:123:facts",
        "osti:topic:heat-transfer:factoids",
        "osti:topic:solar:factoids",
    }
    preserved_keys = {
        "osti:question:query-hash:answer",
        "osti:paper:pdf_bytes:123",
        "osti:paper:text:123",
        "osti:paper:123:metadata",
        "conversation:conv-1",
        "tasks:graph:conv-1",
        "tasks:node:conv-1:task-1",
        "agent:status:conv-1",
        "agent:status_history:conv-1",
    }
    redis_client = _FakeRedis(knowledge_keys | preserved_keys)
    monkeypatch.setattr(runtime, "_get_status_redis_client", lambda: redis_client)
    monkeypatch.setattr(runtime, "store_status_update", lambda *args, **kwargs: None)

    response = asyncio.run(
        debug_commands._maybe_handle_slash_command(
            ConversationRequest(query="/forget", conversation_id="conv-1"),
            "conv-1",
            None,
            [],
        )
    )

    assert response is not None
    assert response.status == "answer"
    assert response.message_metadata == {
        "slash_command": "forget",
        "facts_deleted": 2,
        "index_keys_deleted": 3,
    }
    assert "Forgot 2 stored OSTI knowledge facts." in response.message
    assert knowledge_keys.isdisjoint(redis_client.keys)
    assert preserved_keys <= redis_client.keys


def test_forget_is_a_supported_slash_command() -> None:
    assert debug_commands._is_supported_slash_command_query("/forget") is True
