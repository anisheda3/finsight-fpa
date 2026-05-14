"""asyncpg pool wrapper."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)
_pool: Any | None = None


async def init_db(dsn: str) -> Any:
    """Lazy-import asyncpg and create the pool."""
    global _pool
    try:
        import asyncpg                      # type: ignore
    except ImportError:                     # pragma: no cover
        logger.warning("asyncpg not installed; DB disabled")
        return None
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)
        logger.info("postgres pool initialised")
    return _pool


def get_pool() -> Any | None:
    return _pool


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
