"""Artifact catalog models and storage for cross-agent handoff.

This module is used by :class:`prometheus_api.agent.base.PrometheusAgent` to:
1. Persist conversation-scoped artifact catalog entries
2. Normalize native A2A artifacts into a stable app-facing shape
3. Resolve catalog entries by ID or name for downstream agent calls
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..redis_utils import create_redis_client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_name(name: str) -> str:
    lowered = (name or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class ArtifactReference:
    """Conversation-scoped artifact catalog entry.

    Who uses this:
    - Producer helpers normalize native A2A artifacts into this form for persistence.
    - Orchestrator and downstream agents resolve entries to pass stable IDs between skills.
    - UI/debug endpoints render these entries to show available session artifacts.
    """

    artifact_id: str
    conversation_id: str
    name: str
    description: str
    uri: Optional[str] = None
    mime_type: Optional[str] = None
    json_type: Optional[str] = None
    json_body: Optional[Any] = None
    text_body: Optional[str] = None
    size_bytes: Optional[int] = None
    producer_agent_id: Optional[str] = None
    created_at: str = field(default_factory=_utc_now_iso)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to plain JSON-compatible dictionary for APIs/Redis."""
        payload = asdict(self)
        if payload.get("size_bytes") is not None:
            payload["size_bytes"] = int(payload["size_bytes"])
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ArtifactReference":
        """Parse the normalized internal catalog shape used by Prometheus."""
        return cls(
            artifact_id=str(payload.get("artifact_id") or uuid.uuid4()),
            conversation_id=str(payload.get("conversation_id") or ""),
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            uri=str(payload.get("uri") or "").strip() or None,
            mime_type=payload.get("mime_type"),
            json_type=payload.get("json_type"),
            json_body=payload.get("json_body"),
            text_body=(
                str(payload.get("text_body")) if payload.get("text_body") is not None else None
            ),
            size_bytes=_coerce_int(payload.get("size_bytes")),
            producer_agent_id=payload.get("producer_agent_id"),
            created_at=str(payload.get("created_at") or _utc_now_iso()),
            tags=[str(tag) for tag in (payload.get("tags") or []) if tag is not None],
            metadata=dict(payload.get("metadata") or {}),
        )

    @classmethod
    def from_a2a_artifact(
        cls,
        payload: Any,
        *,
        conversation_id: Optional[str] = None,
        producer_agent_id: Optional[str] = None,
    ) -> Optional["ArtifactReference"]:
        """Normalize a native A2A artifact payload into a catalog entry."""
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json", by_alias=True, exclude_none=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("parts"), list):
            return None

        artifact_metadata = dict(payload.get("metadata") or {})
        created_at = str(artifact_metadata.get("created_at") or _utc_now_iso())
        normalized_conversation_id = str(
            conversation_id or artifact_metadata.get("conversation_id") or ""
        )
        normalized_producer = artifact_metadata.get("producer_agent_id") or producer_agent_id
        normalized_tags = [
            str(tag) for tag in (artifact_metadata.get("tags") or []) if tag is not None
        ]
        name = str(payload.get("name") or "").strip()
        description = str(payload.get("description") or "").strip()
        artifact_id = str(payload.get("artifact_id") or payload.get("artifactId") or uuid.uuid4())
        size_bytes = _coerce_int(artifact_metadata.get("size_bytes"))

        parts = payload.get("parts") or []
        primary_part = parts[0] if parts else None
        if not isinstance(primary_part, dict):
            return None

        part_kind = str(primary_part.get("kind") or "").strip().lower()
        part_metadata = dict(primary_part.get("metadata") or {})

        if part_kind == "file":
            file_payload = dict(primary_part.get("file") or {})
            uri = str(file_payload.get("uri") or "").strip() or None
            mime_type = file_payload.get("mimeType")
            if not name:
                name = str(file_payload.get("name") or "").strip() or "artifact"
            return cls(
                artifact_id=artifact_id,
                conversation_id=normalized_conversation_id,
                name=name,
                description=description,
                uri=uri,
                mime_type=mime_type,
                size_bytes=size_bytes,
                producer_agent_id=normalized_producer,
                created_at=created_at,
                tags=normalized_tags,
                metadata={**artifact_metadata, **part_metadata},
            )

        if part_kind == "data":
            mime_type = part_metadata.get("mime_type") or "application/json"
            return cls(
                artifact_id=artifact_id,
                conversation_id=normalized_conversation_id,
                name=name or "artifact",
                description=description,
                uri=None,
                mime_type=mime_type,
                json_type=(part_metadata.get("json_type")),
                json_body=primary_part.get("data"),
                size_bytes=size_bytes,
                producer_agent_id=normalized_producer,
                created_at=created_at,
                tags=normalized_tags,
                metadata={**artifact_metadata, **part_metadata},
            )

        if part_kind == "text":
            mime_type = part_metadata.get("mime_type") or "text/plain"
            return cls(
                artifact_id=artifact_id,
                conversation_id=normalized_conversation_id,
                name=name or "artifact.txt",
                description=description,
                uri=None,
                mime_type=mime_type,
                text_body=str(primary_part.get("text") or ""),
                size_bytes=size_bytes,
                producer_agent_id=normalized_producer,
                created_at=created_at,
                tags=normalized_tags,
                metadata={**artifact_metadata, **part_metadata},
            )

        return None

    @classmethod
    def from_any(
        cls,
        payload: Any,
        *,
        conversation_id: Optional[str] = None,
        producer_agent_id: Optional[str] = None,
    ) -> Optional["ArtifactReference"]:
        """Parse either a native A2A artifact or the normalized internal catalog shape."""
        normalized = cls.from_a2a_artifact(
            payload,
            conversation_id=conversation_id,
            producer_agent_id=producer_agent_id,
        )
        if normalized is not None:
            return normalized

        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json", by_alias=True, exclude_none=True)

        if not isinstance(payload, dict):
            return None

        if not (
            payload.get("uri")
            or payload.get("json_body") is not None
            or payload.get("text_body") is not None
        ):
            return None

        reference = cls.from_dict(payload)
        if not reference.conversation_id and conversation_id:
            reference.conversation_id = str(conversation_id)
        if not reference.producer_agent_id and producer_agent_id:
            reference.producer_agent_id = str(producer_agent_id)
        return reference

    def to_context_dict(self) -> Dict[str, Any]:
        """Compact, metadata-only view suitable for LLM context injection."""
        return {
            "artifact_id": self.artifact_id,
            "name": self.name,
            "description": self.description[:280] if self.description else "",
            "uri": self.uri,
            "mime_type": self.mime_type,
            "json_type": self.json_type,
            "size_bytes": self.size_bytes,
            "producer_agent_id": self.producer_agent_id,
            "created_at": self.created_at,
            "tags": self.tags,
        }


class ArtifactRegistry:
    """Conversation-scoped artifact catalog with Redis + memory fallback.

    Primary callers:
    - `PrometheusAgent.send_json_artifact` (auto-registration when payload has URI metadata)
    - `PrometheusAgent.send_artifact_reference` (explicit producer helper)
    - Orchestrator routes that resolve artifact IDs/names for skill parameters

    Design intent:
    - Conversation isolation by default
    - Stable opaque IDs for tool/agent invocation
    - Graceful behavior when Redis is unavailable (process-local fallback)
    """

    DEFAULT_TTL_SECONDS = 7 * 24 * 3600

    def __init__(self, redis_url: Optional[str] = None, ttl_seconds: Optional[int] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_password = os.getenv("REDIS_PASSWORD")
        configured_ttl = os.getenv("ARTIFACT_REGISTRY_TTL_SECONDS", "").strip()
        ttl = ttl_seconds
        if ttl is None and configured_ttl:
            try:
                ttl = int(configured_ttl)
            except ValueError:
                ttl = None
        self.ttl_seconds = ttl if ttl is not None else self.DEFAULT_TTL_SECONDS

        self._redis = None
        self._memory_lock = threading.Lock()
        self._memory_store: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._memory_name_to_id: Dict[str, Dict[str, str]] = {}

    def _hash_key(self, conversation_id: str) -> str:
        return f"artifacts:conv:{conversation_id}:by_id"

    def _name_map_key(self, conversation_id: str) -> str:
        return f"artifacts:conv:{conversation_id}:name_to_id"

    def _order_key(self, conversation_id: str) -> str:
        return f"artifacts:conv:{conversation_id}:order"

    def _expires(self, conversation_id: str, client: Any) -> None:
        ttl = self.ttl_seconds
        if ttl <= 0:
            return
        try:
            client.expire(self._hash_key(conversation_id), ttl)
            client.expire(self._name_map_key(conversation_id), ttl)
            client.expire(self._order_key(conversation_id), ttl)
        except Exception:
            pass

    @property
    def redis_client(self):
        if self._redis is None:
            self._redis = create_redis_client(self.redis_url, password=self.redis_password)
        return self._redis

    @staticmethod
    def _timestamp_score(created_at: str) -> float:
        try:
            dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return datetime.now(timezone.utc).timestamp()

    def register(self, reference: ArtifactReference) -> ArtifactReference:
        """Upsert an artifact reference for a conversation and index by name.

        Used by producer-side flows. Name index allows user mentions like
        "mesh output" to be resolved to the canonical artifact ID.
        """
        conversation_id = str(reference.conversation_id or "").strip()
        if not conversation_id:
            raise ValueError("conversation_id is required for artifact registration")
        if not reference.uri and reference.json_body is None and reference.text_body is None:
            raise ValueError("artifact registration requires uri, json_body, or text_body")

        artifact_id = str(reference.artifact_id or uuid.uuid4())
        reference.artifact_id = artifact_id
        if not reference.created_at:
            reference.created_at = _utc_now_iso()

        payload = reference.to_dict()
        normalized_name = _normalize_name(reference.name)
        client = self.redis_client
        if client is not None:
            try:
                client.hset(
                    self._hash_key(conversation_id), artifact_id, json.dumps(payload, default=str)
                )
                client.zadd(
                    self._order_key(conversation_id),
                    {artifact_id: self._timestamp_score(reference.created_at)},
                )
                if normalized_name:
                    client.hset(self._name_map_key(conversation_id), normalized_name, artifact_id)
                self._expires(conversation_id, client)
                return reference
            except Exception:
                # fall through to in-memory fallback
                pass

        with self._memory_lock:
            conv_store = self._memory_store.setdefault(conversation_id, {})
            conv_store[artifact_id] = payload
            if normalized_name:
                self._memory_name_to_id.setdefault(conversation_id, {})[normalized_name] = (
                    artifact_id
                )
        return reference

    def resolve_by_id(self, conversation_id: str, artifact_id: str) -> Optional[ArtifactReference]:
        """Resolve a reference by canonical artifact ID within one conversation."""
        conversation_id = str(conversation_id or "").strip()
        artifact_id = str(artifact_id or "").strip()
        if not conversation_id or not artifact_id:
            return None

        client = self.redis_client
        if client is not None:
            try:
                raw = client.hget(self._hash_key(conversation_id), artifact_id)
                if raw:
                    return ArtifactReference.from_dict(json.loads(raw))
            except Exception:
                pass

        with self._memory_lock:
            raw = self._memory_store.get(conversation_id, {}).get(artifact_id)
            if raw:
                return ArtifactReference.from_dict(raw)
        return None

    def resolve_by_name(
        self, conversation_id: str, name_or_alias: str
    ) -> Optional[ArtifactReference]:
        """Resolve a reference by human name within one conversation."""
        conversation_id = str(conversation_id or "").strip()
        normalized_name = _normalize_name(name_or_alias)
        if not conversation_id or not normalized_name:
            return None

        client = self.redis_client
        if client is not None:
            try:
                artifact_id = client.hget(self._name_map_key(conversation_id), normalized_name)
                if artifact_id:
                    return self.resolve_by_id(conversation_id, artifact_id)
            except Exception:
                pass

        with self._memory_lock:
            artifact_id = self._memory_name_to_id.get(conversation_id, {}).get(normalized_name)
            if artifact_id:
                raw = self._memory_store.get(conversation_id, {}).get(artifact_id)
                if raw:
                    return ArtifactReference.from_dict(raw)
        return None

    def list(self, conversation_id: str, limit: Optional[int] = None) -> List[ArtifactReference]:
        """List newest-first references for a conversation.

        Used by `/api/chat` and artifact catalog endpoints so clients can display
        available artifacts and map names back to IDs.
        """
        conversation_id = str(conversation_id or "").strip()
        if not conversation_id:
            return []
        effective_limit = limit if isinstance(limit, int) and limit > 0 else None

        client = self.redis_client
        if client is not None:
            try:
                if effective_limit:
                    artifact_ids = client.zrevrange(
                        self._order_key(conversation_id), 0, effective_limit - 1
                    )
                else:
                    artifact_ids = client.zrevrange(self._order_key(conversation_id), 0, -1)
                if artifact_ids:
                    payloads = client.hmget(self._hash_key(conversation_id), artifact_ids)
                    items: List[ArtifactReference] = []
                    for raw in payloads:
                        if not raw:
                            continue
                        try:
                            items.append(ArtifactReference.from_dict(json.loads(raw)))
                        except Exception:
                            continue
                    return items
            except Exception:
                pass

        with self._memory_lock:
            values = list(self._memory_store.get(conversation_id, {}).values())
        refs = [ArtifactReference.from_dict(item) for item in values]
        refs.sort(key=lambda ref: self._timestamp_score(ref.created_at), reverse=True)
        if effective_limit:
            refs = refs[:effective_limit]
        return refs

    def clear_conversation(self, conversation_id: str) -> None:
        """Delete all artifact references for one conversation scope."""
        conversation_id = str(conversation_id or "").strip()
        if not conversation_id:
            return

        client = self.redis_client
        if client is not None:
            try:
                client.delete(
                    self._hash_key(conversation_id),
                    self._name_map_key(conversation_id),
                    self._order_key(conversation_id),
                )
                return
            except Exception:
                pass

        with self._memory_lock:
            self._memory_store.pop(conversation_id, None)
            self._memory_name_to_id.pop(conversation_id, None)
