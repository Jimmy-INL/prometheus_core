"""
Capability Cache for dynamic agent discovery.
Caches agent capabilities from registry with TTL-based refresh.
"""
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis

from tool_discovery import REGISTRY_URL, discover_agents, get_agent_card, is_self_agent

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")


@dataclass
class AgentCapability:
    """Represents a single capability (skill) from an agent."""
    agent_id: str
    agent_name: str
    agent_url: str
    skill_id: str
    skill_name: str
    description: str
    supports_streaming: bool = False
    usage_notes: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    input_schema: Dict[str, Any] = field(default_factory=dict)
    expected_duration_seconds: Optional[int] = None
    requires_approval: bool = False
    provides: List[Dict[str, Any]] = field(default_factory=list)
    derivation_rules: List[Dict[str, Any]] = field(default_factory=list)
    execution_priority: Optional[str] = None  # "early" | "normal" | "late" - for sequential ordering

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_url": self.agent_url,
            "supports_streaming": self.supports_streaming,
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "description": self.description,
            "usage_notes": self.usage_notes,
            "tags": self.tags,
            "input_schema": self.input_schema,
            "expected_duration_seconds": self.expected_duration_seconds,
            "requires_approval": self.requires_approval,
            "provides": self.provides,
            "derivation_rules": self.derivation_rules,
            "execution_priority": self.execution_priority,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentCapability":
        """Create from dictionary."""
        return cls(
            agent_id=data["agent_id"],
            agent_name=data["agent_name"],
            agent_url=data["agent_url"],
            supports_streaming=data.get("supports_streaming", False),
            skill_id=data["skill_id"],
            skill_name=data["skill_name"],
            description=data["description"],
            usage_notes=data.get("usage_notes"),
            tags=data.get("tags", []),
            input_schema=data.get("input_schema", {}),
            expected_duration_seconds=data.get("expected_duration_seconds"),
            requires_approval=data.get("requires_approval", False),
            provides=data.get("provides", []),
            derivation_rules=data.get("derivation_rules", []),
            execution_priority=data.get("execution_priority"),
        )


class CapabilityCache:
    """Caches agent capabilities from registry with TTL.

    Provides a local cache of agent capabilities to avoid repeated registry queries.
    Uses Redis for distributed caching with a TTL to ensure capabilities stay fresh
    as the registry evolves.

    Cache strategy:
    - Primary storage: Redis (shared across instances)
    - Fallback storage: In-memory (_local_cache)
    - TTL: 5 minutes (balances freshness vs. registry load)
    """

    TTL_SECONDS = 60  # 1 minute
    CACHE_KEY = "capability_cache:v3:capabilities"
    TIMESTAMP_KEY = "capability_cache:v3:last_refresh"

    def __init__(self, redis_url: Optional[str] = None):
        """Initialize the capability cache.

        Args:
            redis_url: Redis connection URL. Defaults to REDIS_URL env var.
        """
        self.redis_url = redis_url or REDIS_URL
        self.redis_password = REDIS_PASSWORD
        self._redis: Optional[redis.Redis] = None
        self._local_cache: List[AgentCapability] = []
        self._last_refresh: Optional[datetime] = None

    @property
    def redis_client(self) -> redis.Redis:
        """Lazy Redis connection."""
        if self._redis is None:
            self._redis = redis.Redis.from_url(
                self.redis_url,
                password=self.redis_password,
                decode_responses=True
            )
        return self._redis

    def _is_self_capability(self, capability: AgentCapability) -> bool:
        """Return True if capability belongs to this orchestrator instance."""
        return is_self_agent(capability.agent_id, capability.agent_url)

    def _filter_self_capabilities(self, capabilities: List[AgentCapability]) -> List[AgentCapability]:
        """Remove self capabilities to prevent recursive self-invocation."""
        return [cap for cap in capabilities if not self._is_self_capability(cap)]

    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid (within TTL)."""
        try:
            timestamp_str = self.redis_client.get(self.TIMESTAMP_KEY)
            if not timestamp_str:
                return False

            last_refresh = datetime.fromisoformat(timestamp_str)
            age_seconds = (datetime.now(timezone.utc) - last_refresh).total_seconds()
            return age_seconds < self.TTL_SECONDS
        except Exception:
            return False

    async def get_capabilities(self) -> List[AgentCapability]:
        """Get all capabilities, refreshing from registry if needed.

        Returns:
            List of AgentCapability objects
        """
        # Check if we need to refresh
        if not self._is_cache_valid():
            await self.refresh()

        # Try to load from Redis cache
        try:
            cached_data = self.redis_client.get(self.CACHE_KEY)
            if cached_data:
                capabilities_list = json.loads(cached_data)
                capabilities = [AgentCapability.from_dict(c) for c in capabilities_list]
                return self._filter_self_capabilities(capabilities)
        except Exception as e:
            print(f"Warning: Failed to load capabilities from Redis cache: {e}")

        # Fall back to local cache
        return self._filter_self_capabilities(self._local_cache)

    async def refresh(self) -> None:
        """Refresh capabilities from registry."""
        print("Refreshing capability cache from registry...")
        capabilities: List[AgentCapability] = []

        try:
            agents = await discover_agents()

            for agent in agents:
                try:
                    agent_id = agent["agent_id"]       # agent_name (LiteLLM routing key)
                    agent_name = agent.get("name", agent_id)
                    direct_url = agent.get("url", "")   # downstream agent URL (for self-check)

                    if is_self_agent(agent_id, direct_url):
                        print(f"Skipping self agent in capability cache: {agent_id} ({direct_url})")
                        continue

                    # Route all calls through LiteLLM: /a2a/{agent_name}
                    agent_url = f"{REGISTRY_URL}/a2a/{agent_id}"

                    # LiteLLM's /v1/agents payload is a lossy summary and may omit
                    # per-skill inputSchema/approval metadata. Always fetch the
                    # full agent card for capability planning.
                    agent_card = await get_agent_card(agent_id, direct_url=direct_url)
                    if not agent_card.get("skills"):
                        agent_card = agent.get("agent_card_params") or agent_card

                    capabilities_meta = agent_card.get("capabilities") or {}
                    supports_streaming = bool(capabilities_meta.get("streaming", False))

                    # Extract capabilities from each skill
                    for skill in agent_card.get("skills", []):
                        capability = AgentCapability(
                            agent_id=agent_id,
                            agent_name=agent_name,
                            agent_url=agent_url,
                            supports_streaming=supports_streaming,
                            skill_id=skill["id"],
                            skill_name=skill.get("name", skill["id"]),
                            description=skill.get("description", ""),
                            usage_notes=skill.get("usage_notes"),
                            tags=skill.get("tags", []),
                            input_schema=skill.get("inputSchema", {}),
                            expected_duration_seconds=skill.get("expected_duration_seconds"),
                            requires_approval=skill.get("requires_approval", False),
                            provides=skill.get("provides", []),
                            derivation_rules=skill.get("derivation_rules", []),
                            execution_priority=skill.get("execution_priority"),
                        )
                        capabilities.append(capability)
                        print(f"  Cached capability: {capability.skill_id} from {agent_id}")

                except Exception as e:
                    print(f"Warning: Failed to fetch capabilities for agent {agent.get('agent_id', 'unknown')}: {e}")
                    continue

            # Store in Redis cache
            try:
                capabilities_json = json.dumps([c.to_dict() for c in capabilities])
                self.redis_client.set(self.CACHE_KEY, capabilities_json)
                self.redis_client.set(
                    self.TIMESTAMP_KEY,
                    datetime.now(timezone.utc).isoformat()
                )
            except Exception as e:
                print(f"Warning: Failed to store capabilities in Redis: {e}")

            # Update local cache
            self._local_cache = self._filter_self_capabilities(capabilities)
            self._last_refresh = datetime.now(timezone.utc)

            print(f"Capability cache refreshed: {len(self._local_cache)} capabilities")

        except Exception as e:
            print(f"Error refreshing capability cache: {e}")
            # Keep existing cache on failure

    def get_by_skill_id(self, skill_id: str) -> Optional[AgentCapability]:
        """Get capability by skill ID from local cache.

        Args:
            skill_id: The skill ID to find

        Returns:
            AgentCapability or None if not found
        """
        for cap in self._local_cache:
            if cap.skill_id == skill_id:
                return cap
        return None

    async def get_capability_by_skill_id(self, skill_id: str) -> Optional[AgentCapability]:
        """Get capability by skill ID, refreshing cache if needed.

        This async method ensures the cache is populated before lookup.

        Args:
            skill_id: The skill ID to find

        Returns:
            AgentCapability or None if not found
        """
        # Ensure cache is populated
        if not self._local_cache or not self._is_cache_valid():
            await self.refresh()

        # Try local cache first
        capability = self.get_by_skill_id(skill_id)
        if capability:
            return None if self._is_self_capability(capability) else capability

        # Try loading from Redis if local cache doesn't have it
        try:
            cached_data = self.redis_client.get(self.CACHE_KEY)
            if cached_data:
                capabilities_list = json.loads(cached_data)
                for cap_dict in capabilities_list:
                    if cap_dict.get("skill_id") == skill_id:
                        capability = AgentCapability.from_dict(cap_dict)
                        return None if self._is_self_capability(capability) else capability
        except Exception as e:
            print(f"Warning: Failed to lookup capability from Redis: {e}")

        return None

    def get_by_tag(self, tag: str) -> List[AgentCapability]:
        """Get capabilities matching a tag from local cache.

        Args:
            tag: Tag to search for

        Returns:
            List of matching AgentCapability objects
        """
        return [cap for cap in self._local_cache if tag in cap.tags]

    def get_by_agent_id(self, agent_id: str) -> List[AgentCapability]:
        """Get all capabilities for a specific agent.

        Args:
            agent_id: The agent ID to filter by

        Returns:
            List of AgentCapability objects for that agent
        """
        return [cap for cap in self._local_cache if cap.agent_id == agent_id]

    def clear(self) -> None:
        """Clear the cache."""
        try:
            self.redis_client.delete(self.CACHE_KEY)
            self.redis_client.delete(self.TIMESTAMP_KEY)
        except Exception as e:
            logger.warning(f"Failed to clear Redis cache: {e}")
        self._local_cache = []
        self._last_refresh = None


# Singleton instance
_capability_cache: Optional[CapabilityCache] = None


def get_capability_cache() -> CapabilityCache:
    """Get or create the singleton CapabilityCache instance.

    Returns:
        CapabilityCache instance
    """
    global _capability_cache
    if _capability_cache is None:
        _capability_cache = CapabilityCache()
    return _capability_cache
