"""Memory Manager for persistent storage and retrieval of analysis factoids.

This module manages the persistent memory system that allows the nuclear analysis
agent to learn from past analyses and recall relevant information for future work.
"""

import json
import math
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis


class MemoryManager:
    """Manages persistent memory storage and retrieval using Redis.

    Stores factoids extracted from completed analyses with semantic indexing
    for efficient retrieval based on material, analysis type, and similarity.
    """

    def __init__(self, redis_url: str):
        """Initialize the memory manager with Redis connection.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379)
        """
        self.redis_client = redis.Redis.from_url(redis_url, decode_responses=True)

    def store_factoid(self, factoid: Dict[str, Any]) -> str:
        """Store a factoid with indexes for fast retrieval.

        Args:
            factoid: Factoid dictionary with content, material_id, analysis_type, etc.

        Returns:
            The factoid ID (UUID string)
        """
        factoid_id = factoid.get("factoid_id") or str(uuid.uuid4())
        factoid["factoid_id"] = factoid_id

        # Store full factoid as JSON
        self.redis_client.set(
            f"factoid:{factoid_id}",
            json.dumps(factoid)
        )

        # Add to material index for fast material lookup
        if factoid.get("material_id"):
            self.redis_client.sadd(
                f"material:{factoid['material_id']}:factoids",
                factoid_id
            )

        # Add to analysis type index
        if factoid.get("analysis_type"):
            self.redis_client.sadd(
                f"analysis_type:{factoid['analysis_type']}:factoids",
                factoid_id
            )

        # Add to global embeddings index
        if factoid.get("embedding"):
            self.redis_client.zadd(
                "embeddings:index",
                {factoid_id: 0}  # Score 0 for sorted set (unused for now)
            )

        return factoid_id

    def get_factoids_by_material(self, material_id: str) -> List[Dict[str, Any]]:
        """Retrieve all factoids for a specific material.

        Args:
            material_id: Material identifier (e.g., "SS316")

        Returns:
            List of factoid dictionaries
        """
        factoid_ids = self.redis_client.smembers(f"material:{material_id}:factoids")
        factoids = []

        for fid in factoid_ids:
            data = self.redis_client.get(f"factoid:{fid}")
            if data:
                factoids.append(json.loads(data))

        return factoids

    def get_factoids_by_analysis_type(
        self,
        analysis_type: str
    ) -> List[Dict[str, Any]]:
        """Retrieve all factoids for a specific analysis type.

        Args:
            analysis_type: Analysis type (e.g., "corrosion", "radiation")

        Returns:
            List of factoid dictionaries
        """
        factoid_ids = self.redis_client.smembers(
            f"analysis_type:{analysis_type}:factoids"
        )
        factoids = []

        for fid in factoid_ids:
            data = self.redis_client.get(f"factoid:{fid}")
            if data:
                factoids.append(json.loads(data))

        return factoids

    def search_similar_factoids(
        self,
        query_embedding: List[float],
        material_id: Optional[str] = None,
        top_k: int = 5,
        min_similarity: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Find factoids with similar embeddings using cosine similarity.

        Args:
            query_embedding: Embedding vector for the query
            material_id: Optional material ID to filter results
            top_k: Maximum number of results to return
            min_similarity: Minimum cosine similarity threshold (0.0-1.0)

        Returns:
            List of factoids sorted by similarity (highest first)
        """
        # Get candidate factoids
        if material_id:
            factoid_ids = self.redis_client.smembers(
                f"material:{material_id}:factoids"
            )
        else:
            factoid_ids = self.redis_client.zrange("embeddings:index", 0, -1)

        # Calculate similarities
        similarities = []
        for fid in factoid_ids:
            data = self.redis_client.get(f"factoid:{fid}")
            if data:
                factoid = json.loads(data)
                if "embedding" in factoid and factoid["embedding"]:
                    similarity = self._cosine_similarity(
                        query_embedding,
                        factoid["embedding"]
                    )
                    if similarity >= min_similarity:
                        similarities.append((similarity, factoid))

        # Sort by similarity and return top_k
        similarities.sort(reverse=True, key=lambda x: x[0])
        return [factoid for score, factoid in similarities[:top_k]]

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity score (0.0-1.0)
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = math.sqrt(sum(a * a for a in vec1))
        mag2 = math.sqrt(sum(b * b for b in vec2))

        return dot / (mag1 * mag2) if mag1 and mag2 else 0.0

    def store_conversation(self, conv_id: str, state: Dict) -> None:
        """Store conversation state in Redis (replaces in-memory dict).

        Args:
            conv_id: Conversation ID
            state: Conversation state dictionary
        """
        self.redis_client.set(
            f"conversation:{conv_id}",
            json.dumps(state, default=str)
            # No TTL - permanent storage
        )

    def get_conversation(self, conv_id: str) -> Optional[Dict]:
        """Retrieve conversation state from Redis.

        Args:
            conv_id: Conversation ID

        Returns:
            Conversation state dictionary or None if not found
        """
        data = self.redis_client.get(f"conversation:{conv_id}")
        return json.loads(data) if data else None

    def get_all_factoids(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve all factoids (for debugging/browsing).

        Args:
            limit: Maximum number of factoids to return

        Returns:
            List of factoid dictionaries
        """
        # Get all factoid keys
        keys = self.redis_client.keys("factoid:*")
        factoids = []

        for key in keys[:limit]:
            data = self.redis_client.get(key)
            if data:
                factoids.append(json.loads(data))

        return factoids

    def delete_factoid(self, factoid_id: str) -> bool:
        """Delete a factoid and all its indexes.

        Args:
            factoid_id: Factoid ID to delete

        Returns:
            True if deleted, False if not found
        """
        # Get factoid to find indexes
        data = self.redis_client.get(f"factoid:{factoid_id}")
        if not data:
            return False

        factoid = json.loads(data)

        # Remove from material index
        if factoid.get("material_id"):
            self.redis_client.srem(
                f"material:{factoid['material_id']}:factoids",
                factoid_id
            )

        # Remove from analysis type index
        if factoid.get("analysis_type"):
            self.redis_client.srem(
                f"analysis_type:{factoid['analysis_type']}:factoids",
                factoid_id
            )

        # Remove from embeddings index
        self.redis_client.zrem("embeddings:index", factoid_id)

        # Delete the factoid itself
        self.redis_client.delete(f"factoid:{factoid_id}")

        return True


# Singleton instance
_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """Get or create the singleton MemoryManager instance.

    Returns:
        MemoryManager instance connected to Redis
    """
    global _memory_manager
    if _memory_manager is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _memory_manager = MemoryManager(redis_url)
    return _memory_manager


