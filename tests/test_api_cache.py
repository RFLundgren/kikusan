"""Tests for kikusan.web.api_cache.TtlCache."""

import time
from unittest.mock import patch

from kikusan.web.api_cache import TtlCache


class TestTtlCacheGetPut:
    def test_miss_returns_none(self):
        cache = TtlCache()
        assert cache.get("nonexistent") is None

    def test_hit_returns_value(self):
        cache = TtlCache()
        cache.put("key", {"data": 42})
        assert cache.get("key") == {"data": 42}

    def test_overwrite_existing_key(self):
        cache = TtlCache()
        cache.put("key", "old")
        cache.put("key", "new")
        assert cache.get("key") == "new"

    def test_expiry_returns_none(self):
        cache = TtlCache(ttl_seconds=10)
        with patch("kikusan.web.api_cache.time") as mock_time:
            mock_time.monotonic.return_value = 100.0
            cache.put("key", "value")

            # Still valid at t=109
            mock_time.monotonic.return_value = 109.0
            assert cache.get("key") == "value"

            # Expired at t=111
            mock_time.monotonic.return_value = 111.0
            assert cache.get("key") is None

    def test_lru_eviction(self):
        cache = TtlCache(max_entries=2, ttl_seconds=3600)
        cache.put("a", 1)
        cache.put("b", 2)
        # "a" is oldest, adding "c" should evict it
        cache.put("c", 3)

        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_lru_access_refreshes_order(self):
        cache = TtlCache(max_entries=2, ttl_seconds=3600)
        cache.put("a", 1)
        cache.put("b", 2)
        # Access "a" to make it most-recently-used
        cache.get("a")
        # Now "b" is oldest, adding "c" should evict "b"
        cache.put("c", 3)

        assert cache.get("a") == 1
        assert cache.get("b") is None
        assert cache.get("c") == 3


class TestTtlCacheCachedCall:
    def test_cached_call_miss_calls_fn(self):
        cache = TtlCache()
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            return "result"

        result = cache.cached_call("key", fn)
        assert result == "result"
        assert call_count == 1

    def test_cached_call_hit_skips_fn(self):
        cache = TtlCache()
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            return "result"

        cache.cached_call("key", fn)
        result = cache.cached_call("key", fn)
        assert result == "result"
        assert call_count == 1

    def test_cached_call_after_expiry_calls_fn_again(self):
        cache = TtlCache(ttl_seconds=10)
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            return f"result-{call_count}"

        with patch("kikusan.web.api_cache.time") as mock_time:
            mock_time.monotonic.return_value = 100.0
            result1 = cache.cached_call("key", fn)
            assert result1 == "result-1"

            mock_time.monotonic.return_value = 111.0
            result2 = cache.cached_call("key", fn)
            assert result2 == "result-2"
            assert call_count == 2
