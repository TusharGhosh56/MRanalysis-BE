import time
from threading import Lock
from typing import Any
from uuid import UUID

from app.config import get_settings

settings = get_settings()

ANALYTICS_KEY_ALL = "analytics:{repo_id}"
ANALYTICS_KEY_METRIC = "analytics:{repo_id}:{metric}"
PROGRESS_KEY = "repo:{repo_id}:progress"


class InMemoryTTLCache:
    """Thread-safe in-memory cache with TTL and capacity limit."""

    def __init__(self, maxsize: int = 2048, default_ttl: int = 300) -> None:
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = Lock()
        self._maxsize = maxsize
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._cache.get(key)
            if item is None:
                return None
            expires_at, val = item
            if time.monotonic() > expires_at:
                del self._cache[key]
                return None
            return val

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            now = time.monotonic()
            if len(self._cache) >= self._maxsize and key not in self._cache:
                expired = [k for k, (exp, _) in self._cache.items() if now > exp]
                for k in expired:
                    del self._cache[k]
                if len(self._cache) >= self._maxsize:
                    oldest_key = next(iter(self._cache))
                    del self._cache[oldest_key]
            self._cache[key] = (now + ttl, value)

    def delete(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._cache.pop(k, None)

    def delete_prefix(self, prefix: str) -> None:
        with self._lock:
            matching_keys = [k for k in self._cache if k.startswith(prefix)]
            for k in matching_keys:
                del self._cache[k]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


_cache = InMemoryTTLCache()


def get_cache_instance() -> InMemoryTTLCache:
    return _cache


def set_repo_progress(repo_id: UUID, *, stage: str, progress_pct: int) -> None:
    _cache.set(
        PROGRESS_KEY.format(repo_id=repo_id),
        {"stage": stage, "progress_pct": progress_pct},
        ttl=86400,
    )


def get_repo_progress(repo_id: UUID) -> dict[str, Any] | None:
    return _cache.get(PROGRESS_KEY.format(repo_id=repo_id))


def invalidate_analytics_cache(repo_id: UUID) -> None:
    _cache.delete(ANALYTICS_KEY_ALL.format(repo_id=repo_id))
    _cache.delete_prefix(f"analytics:{repo_id}:")


def get_cached_analytics(repo_id: UUID, metric: str | None = None) -> Any | None:
    key = (
        ANALYTICS_KEY_ALL.format(repo_id=repo_id)
        if metric is None
        else ANALYTICS_KEY_METRIC.format(repo_id=repo_id, metric=metric)
    )
    return _cache.get(key)


def set_cached_analytics(repo_id: UUID, data: Any, metric: str | None = None) -> None:
    key = (
        ANALYTICS_KEY_ALL.format(repo_id=repo_id)
        if metric is None
        else ANALYTICS_KEY_METRIC.format(repo_id=repo_id, metric=metric)
    )
    _cache.set(key, data, ttl=settings.ANALYTICS_CACHE_TTL_SECONDS)

