"""Redis client wrapper."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)
_client: Any | None = None


def init_redis(url: str) -> Any:
    global _client
    try:
        import redis                                # type: ignore
    except ImportError:                              # pragma: no cover
        logger.warning("redis-py not installed; redis disabled")
        return None
    if _client is None:
        _client = redis.Redis.from_url(url, decode_responses=True)
        try:
            _client.ping()
            logger.info("redis client initialised")
        except Exception as e:
            logger.warning("redis ping failed: %s", e)
    return _client


def get_client() -> Any | None:
    return _client
