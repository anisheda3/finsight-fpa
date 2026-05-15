"""
MemoryManager — shared cross-run memory backed by PostgreSQL.

Spec requires:
    • all agents share a MemoryManager
    • cross-run persistence (e.g. ForecastingAgent recalls last month's model)
    • at least one agent calls memory.search before producing output

This wraps the agent_memory table with simple put/get/search APIs and exposes
a synchronous + async interface so it works inside Temporal activities and
FastAPI endpoints alike.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    company_id: str | None
    agent_name: str
    memory_key: str
    memory_value: dict[str, Any]
    tags: list[str]


class MemoryManager:
    """
    Async-friendly. Holds a reference to an asyncpg pool (injected from
    app.core.db).  If pool is None, falls back to in-process dict (useful for
    unit tests).
    """
    def __init__(self, pool: Any | None = None) -> None:
        self._pool = pool
        self._mem: dict[tuple[str | None, str, str], dict[str, Any]] = {}

    # ─── put ─────────────────────────────────────────────────
    async def put(
        self,
        agent_name: str,
        memory_key: str,
        memory_value: dict[str, Any],
        company_id: UUID | str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        cid = str(company_id) if company_id else None
        if self._pool is None:
            self._mem[(cid, agent_name, memory_key)] = memory_value
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_memory (company_id, agent_name, memory_key,
                                          memory_value, tags, updated_at)
                VALUES ($1, $2, $3, $4::jsonb, $5, NOW())
                ON CONFLICT DO NOTHING
                """,
                cid, agent_name, memory_key, json.dumps(memory_value), tags or [],
            )

    # ─── get ─────────────────────────────────────────────────
    async def get(
        self,
        agent_name: str,
        memory_key: str,
        company_id: UUID | str | None = None,
    ) -> dict[str, Any] | None:
        cid = str(company_id) if company_id else None
        if self._pool is None:
            return self._mem.get((cid, agent_name, memory_key))
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT memory_value FROM agent_memory
                WHERE company_id IS NOT DISTINCT FROM $1
                  AND agent_name = $2 AND memory_key = $3
                ORDER BY updated_at DESC LIMIT 1
                """,
                cid, agent_name, memory_key,
            )
            if not row:
                return None
            v = row["memory_value"]
            return json.loads(v) if isinstance(v, str) else v

    # ─── search ──────────────────────────────────────────────
    async def search(
        self,
        agent_name: str,
        company_id: UUID | str | None = None,
        tag_any: list[str] | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        cid = str(company_id) if company_id else None
        if self._pool is None:
            out = []
            for (c, a, k), v in self._mem.items():
                if a != agent_name:
                    continue
                if cid is not None and c != cid:
                    continue
                out.append(MemoryEntry(c, a, k, v, []))
            return out[:limit]
        async with self._pool.acquire() as conn:
            if tag_any:
                rows = await conn.fetch(
                    """
                    SELECT company_id, agent_name, memory_key, memory_value, tags
                    FROM agent_memory
                    WHERE agent_name = $1
                      AND (company_id IS NOT DISTINCT FROM $2)
                      AND tags && $3
                    ORDER BY updated_at DESC LIMIT $4
                    """,
                    agent_name, cid, tag_any, limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT company_id, agent_name, memory_key, memory_value, tags
                    FROM agent_memory
                    WHERE agent_name = $1
                      AND (company_id IS NOT DISTINCT FROM $2)
                    ORDER BY updated_at DESC LIMIT $3
                    """,
                    agent_name, cid, limit,
                )
        return [
            MemoryEntry(
                company_id=str(r["company_id"]) if r["company_id"] else None,
                agent_name=r["agent_name"],
                memory_key=r["memory_key"],
                memory_value=json.loads(r["memory_value"])
                              if isinstance(r["memory_value"], str) else r["memory_value"],
                tags=list(r["tags"] or []),
            )
            for r in rows
        ]

    async def create_user_memories(self, *args, **kwargs) -> None:
        """Required by Agno's agent protocol. No-op for now."""
        return None


# Process-wide singleton, configured at startup
_GLOBAL_MEMORY: MemoryManager | None = None


def init_memory(pool: Any | None) -> MemoryManager:
    global _GLOBAL_MEMORY
    _GLOBAL_MEMORY = MemoryManager(pool)
    return _GLOBAL_MEMORY


def get_memory() -> MemoryManager:
    global _GLOBAL_MEMORY
    if _GLOBAL_MEMORY is None:
        _GLOBAL_MEMORY = MemoryManager(None)        # in-memory fallback
    return _GLOBAL_MEMORY
