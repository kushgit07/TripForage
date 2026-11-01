"""A tiny process-local TTL cache for search results.

The original project called SerpAPI fresh on every single query, including
retries and duplicate user questions. On a free-tier quota (Duffel test mode,
SerpAPI free tier, etc.) that burns through the monthly allowance fast. This
cache means "same search twice within N minutes" costs one API call, not two.

In-memory only, one cache per process. That's the right tradeoff for a small
single-instance demo app; if this ever runs as multiple replicas, swap
`TTLCache` for a Redis-backed cache with the same `get`/`set` interface.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from cachetools import TTLCache


def make_cache_key(**kwargs: Any) -> str:
    """Build a stable cache key from search parameters, regardless of key order."""
    payload = json.dumps(kwargs, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SearchCache:
    def __init__(self, ttl_seconds: int, maxsize: int = 256) -> None:
        self._store: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl_seconds)

    def get(self, key: str) -> Any | None:
        return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value
