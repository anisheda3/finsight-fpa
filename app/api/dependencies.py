"""FastAPI dependencies — DB pool, redis, etc."""
from __future__ import annotations

from app.core.db import get_pool
from app.core.redis import get_client


def db_pool():
    return get_pool()


def redis_client():
    return get_client()
