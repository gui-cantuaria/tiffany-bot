"""
Tiffany OS — Community Knowledge Graph & Semantic Memory Layer
=============================================================
Defines an extensible abstraction over semantic long-term memory for communities.
Allows ingesting conversation summaries, voice meeting decisions, and project
context with vector similarity queries (ready for PostgreSQL pgvector, Neo4j, or Qdrant).
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

log = logging.getLogger("tiffany.core.knowledge")

@dataclass
class MemoryNode:
    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    guild_id: int = 0
    node_type: str = "voice_meeting_summary"  # voice_meeting_summary, project_decision, community_preference
    content: str = ""
    tags: List[str] = field(default_factory=list)
    embedding_vector: Optional[List[float]] = None
    created_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())

class CommunityKnowledgeGraph:
    """
    In-memory / transactional storage gateway abstraction for indexing server knowledge
    without tying persistence details to Discord command syntax.
    """
    def __init__(self) -> None:
        # Map: guild_id -> List[MemoryNode]
        self._store: Dict[int, List[MemoryNode]] = {}

    async def ingest_memory(
        self, 
        guild_id: int, 
        content: str, 
        node_type: str = "summary", 
        tags: Optional[List[str]] = None
    ) -> MemoryNode:
        node = MemoryNode(
            guild_id=guild_id,
            node_type=node_type,
            content=content,
            tags=tags or []
        )
        if guild_id not in self._store:
            self._store[guild_id] = []
        self._store[guild_id].append(node)
        log.debug("Ingested node %s (%s) into Knowledge Graph for guild %d", node.node_id, node_type, guild_id)
        return node

    async def semantic_search(self, guild_id: int, query_text: str, limit: int = 5) -> List[MemoryNode]:
        """
        Simulates cosine similarity / full-text tag relevance lookup over community nodes.
        In production, delegates to 'SELECT * FROM knowledge_graph ORDER BY embedding <-> $1'.
        """
        nodes = self._store.get(guild_id, [])
        if not nodes:
            return []

        query_lower = query_text.lower().split()
        scored: List[tuple[int, MemoryNode]] = []
        
        for n in nodes:
            score = 0
            # Simple keyword matching score simulation for deterministic testing
            content_lower = n.content.lower()
            for word in query_lower:
                if len(word) > 2 and word in content_lower:
                    score += 1
            for tag in n.tags:
                if any(t in tag.lower() for t in query_lower):
                    score += 2
            if score > 0 or not query_text.strip():
                scored.append((score, n))
                
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

knowledge_graph = CommunityKnowledgeGraph()
