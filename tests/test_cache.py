import time
from uuid import uuid4

from app.core.cache import (
    InMemoryTTLCache,
    get_cached_analytics,
    get_repo_progress,
    invalidate_analytics_cache,
    set_cached_analytics,
    set_repo_progress,
)


def test_in_memory_ttl_cache_basic():
    cache = InMemoryTTLCache(maxsize=10, default_ttl=60)
    cache.set("key1", {"value": 42})
    assert cache.get("key1") == {"value": 42}
    assert cache.get("nonexistent") is None


def test_in_memory_ttl_cache_expiration():
    cache = InMemoryTTLCache(maxsize=10, default_ttl=1)
    cache.set("key1", "val1", ttl=0.01)
    time.sleep(0.02)
    assert cache.get("key1") is None


def test_in_memory_ttl_cache_eviction():
    cache = InMemoryTTLCache(maxsize=2, default_ttl=60)
    cache.set("k1", "v1")
    cache.set("k2", "v2")
    cache.set("k3", "v3")  # Exceeds maxsize, should evict k1
    assert cache.get("k1") is None
    assert cache.get("k2") == "v2"
    assert cache.get("k3") == "v3"


def test_in_memory_ttl_cache_delete_and_prefix():
    cache = InMemoryTTLCache()
    cache.set("analytics:1", "data1")
    cache.set("analytics:1:summary", "summary1")
    cache.set("analytics:2", "data2")

    cache.delete_prefix("analytics:1")
    assert cache.get("analytics:1") is None
    assert cache.get("analytics:1:summary") is None
    assert cache.get("analytics:2") == "data2"


def test_progress_helpers():
    repo_id = uuid4()
    set_repo_progress(repo_id, stage="parsing", progress_pct=45)
    progress = get_repo_progress(repo_id)
    assert progress is not None
    assert progress["stage"] == "parsing"
    assert progress["progress_pct"] == 45


def test_analytics_cache_helpers():
    repo_id = uuid4()
    set_cached_analytics(repo_id, {"total": 100})
    set_cached_analytics(repo_id, {"bus_factor": 2}, metric="bus_factor")

    assert get_cached_analytics(repo_id) == {"total": 100}
    assert get_cached_analytics(repo_id, metric="bus_factor") == {"bus_factor": 2}

    invalidate_analytics_cache(repo_id)
    assert get_cached_analytics(repo_id) is None
    assert get_cached_analytics(repo_id, metric="bus_factor") is None
