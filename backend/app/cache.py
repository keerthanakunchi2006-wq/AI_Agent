"""Cache abstraction with a Redis or in-memory backend.

If ``REDIS_URL`` is set and Redis is reachable we use it; otherwise we fall
back to a process-local TTL cache. This keeps the app runnable without Redis
while preserving the production path.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from .config import settings

try:
    import redis  # type: ignore
    _REDIS_CLIENT = redis.from_url(settings.REDIS_URL) if settings.REDIS_URL else None
    if _REDIS_CLIENT is not None:
        _REDIS_CLIENT.ping()
except Exception:
    _REDIS_CLIENT = None


class _MemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if not item:
            return None
        value, expiry = item
        if expiry and expiry < time.time():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        expiry = time.time() + ttl if ttl else 0
        self._store[key] = (value, expiry)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def flush(self) -> None:
        self._store.clear()


_mem = _MemoryCache()


def cache_get_json(key: str) -> Optional[Any]:
    if _REDIS_CLIENT is not None:
        raw = _REDIS_CLIENT.get(key)
        return json.loads(raw) if raw else None
    return _mem.get(key)


def cache_set_json(key: str, value: Any, ttl: int = 300) -> None:
    if _REDIS_CLIENT is not None:
        _REDIS_CLIENT.setex(key, ttl, json.dumps(value))
    else:
        _mem.set(key, value, ttl)


def cache_delete(key: str) -> None:
    if _REDIS_CLIENT is not None:
        _REDIS_CLIENT.delete(key)
    else:
        _mem.delete(key)


def cache_backend() -> str:
    return "redis" if _REDIS_CLIENT is not None else "memory"
