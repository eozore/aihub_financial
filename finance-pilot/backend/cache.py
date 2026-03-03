"""Simple in-memory TTL cache for dashboard and trend queries."""
import os
import time
import logging
from typing import Any, Optional

logger = logging.getLogger("finance-pilot")

CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "300"))  # 5 min default
CACHE_ENABLED = os.environ.get("CACHE_ENABLED", "true").lower() == "true"


class TTLCache:
    """Thread-safe in-memory cache with per-key TTL.

    For single-instance deployments (Cloud Run with max 1 instance) this is
    sufficient. For multi-instance, swap to Redis.
    """

    def __init__(self, default_ttl: int = CACHE_TTL_SECONDS):
        self._store: dict[str, tuple[float, Any]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        if not CACHE_ENABLED:
            return None
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if not CACHE_ENABLED:
            return
        self._store[key] = (time.time() + (ttl or self._default_ttl), value)

    def invalidate_prefix(self, prefix: str) -> int:
        """Remove all keys starting with *prefix*. Returns count removed."""
        to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in to_delete:
            del self._store[k]
        return len(to_delete)

    def clear(self) -> None:
        self._store.clear()


# Singleton used across the app
dashboard_cache = TTLCache()
