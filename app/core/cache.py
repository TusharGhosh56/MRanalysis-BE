import json
from functools import lru_cache
from typing import Any
from uuid import UUID

import redis

from app.config import get_settings

settings = get_settings()

ANALYTICS_KEY_ALL = "analytics:{repo_id}"
ANALYTICS_KEY_METRIC = "analytics:{repo_id}:{metric}"
PROGRESS_KEY = "repo:{repo_id}:progress"


@lru_cache
def get_redis_client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _redis_get(client: redis.Redis, key: str) -> str | None:
    try:
        return client.get(key)
    except redis.RedisError:
        return None


def _redis_setex(client: redis.Redis, key: str, ttl: int, value: str) -> None:
    try:
        client.setex(key, ttl, value)
    except redis.RedisError:
        return None


def _redis_delete(client: redis.Redis, *keys: str) -> None:
    try:
        if keys:
            client.delete(*keys)
    except redis.RedisError:
        return None


def set_repo_progress(repo_id: UUID, *, stage: str, progress_pct: int) -> None:
    client = get_redis_client()
    _redis_setex(
        client,
        PROGRESS_KEY.format(repo_id=repo_id),
        86400,
        json.dumps({"stage": stage, "progress_pct": progress_pct}),
    )


def get_repo_progress(repo_id: UUID) -> dict[str, Any] | None:
    client = get_redis_client()
    raw = _redis_get(client, PROGRESS_KEY.format(repo_id=repo_id))
    if not raw:
        return None
    return json.loads(raw)


def invalidate_analytics_cache(repo_id: UUID) -> None:
    client = get_redis_client()
    pattern = ANALYTICS_KEY_METRIC.format(repo_id=repo_id, metric="*")
    keys = [ANALYTICS_KEY_ALL.format(repo_id=repo_id)]
    try:
        keys.extend(client.scan_iter(match=pattern))
    except redis.RedisError:
        return
    _redis_delete(client, *keys)


def get_cached_analytics(repo_id: UUID, metric: str | None = None) -> Any | None:
    client = get_redis_client()
    key = (
        ANALYTICS_KEY_ALL.format(repo_id=repo_id)
        if metric is None
        else ANALYTICS_KEY_METRIC.format(repo_id=repo_id, metric=metric)
    )
    raw = _redis_get(client, key)
    if raw is None:
        return None
    return json.loads(raw)


def set_cached_analytics(repo_id: UUID, data: Any, metric: str | None = None) -> None:
    client = get_redis_client()
    key = (
        ANALYTICS_KEY_ALL.format(repo_id=repo_id)
        if metric is None
        else ANALYTICS_KEY_METRIC.format(repo_id=repo_id, metric=metric)
    )
    _redis_setex(
        client, key, settings.ANALYTICS_CACHE_TTL_SECONDS, json.dumps(data, default=str)
    )
