"""
Tests for caching functionality.

This module tests the TTL-based LRU cache implementation and the
cache decorators for database operations.
"""

import asyncio
import time
from typing import List

import pytest

from app.core.cache import (
    TTLCache,
    cache_frame,
    cache_range,
    get_cache_stats,
    clear_all_caches,
    cleanup_expired_entries,
)


class TestTTLCache:
    """Test TTLCache class directly."""
    
    def test_cache_basic_operations(self):
        """Test basic get/set operations."""
        cache = TTLCache(max_size=3, ttl_seconds=60)
        
        # Set and get values
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        assert cache.get("nonexistent") is None
    
    def test_cache_expiration(self):
        """Test TTL expiration."""
        cache = TTLCache(max_size=10, ttl_seconds=0.1)  # 100ms TTL
        
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        
        # Wait for expiration
        time.sleep(0.15)
        assert cache.get("key1") is None
    
    def test_cache_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = TTLCache(max_size=3, ttl_seconds=60)
        
        # Fill cache
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        
        # Access key1 to make it recently used
        cache.get("key1")
        
        # Add new item, should evict key2 (least recently used)
        cache.set("key4", "value4")
        
        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"
    
    def test_cache_stats(self):
        """Test statistics tracking."""
        cache = TTLCache(max_size=3, ttl_seconds=60)
        
        # Initial stats
        stats = cache.stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0
        assert stats["evictions"] == 0
        
        # Add items and track hits/misses
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key2")  # Miss
        
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["hit_rate_percent"] == 50.0
    
    def test_cache_cleanup_expired(self):
        """Test manual cleanup of expired entries."""
        cache = TTLCache(max_size=10, ttl_seconds=0.1)  # 100ms TTL
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        # Wait for expiration
        time.sleep(0.15)
        
        # Before cleanup, size still shows 2 (lazy expiration)
        stats_before = cache.stats()
        
        # Manual cleanup
        removed = cache.cleanup_expired()
        assert removed == 2
        
        stats_after = cache.stats()
        assert stats_after["size"] == 0
        assert stats_after["expirations"] == stats_before["expirations"] + 2
    
    def test_cache_clear(self):
        """Test clearing entire cache."""
        cache = TTLCache(max_size=10, ttl_seconds=60)
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        assert cache.stats()["size"] == 2
        
        cache.clear()
        assert cache.stats()["size"] == 0
        assert cache.get("key1") is None


class TestCacheDecorators:
    """Test cache decorators for functions."""
    
    @pytest.fixture(autouse=True)
    def clear_caches(self):
        """Clear all caches before each test."""
        clear_all_caches()
        yield
        clear_all_caches()
    
    @pytest.mark.asyncio
    async def test_cache_frame_decorator(self):
        """Test @cache_frame decorator caches single values."""
        call_count = 0
        
        @cache_frame(ttl_seconds=60)
        async def get_value(depth: float):
            nonlocal call_count
            call_count += 1
            return f"value_{depth}"
        
        # First call - cache miss
        result1 = await get_value(100.0)
        assert result1 == "value_100.0"
        assert call_count == 1
        
        # Second call - cache hit
        result2 = await get_value(100.0)
        assert result2 == "value_100.0"
        assert call_count == 1  # Function not called again
        
        # Different depth - cache miss
        result3 = await get_value(200.0)
        assert result3 == "value_200.0"
        assert call_count == 2
        
        # Verify stats
        stats = get_cache_stats()
        assert stats["frame_cache"]["hits"] == 1
        assert stats["frame_cache"]["misses"] == 2
    
    @pytest.mark.asyncio
    async def test_cache_frame_none_not_cached(self):
        """Test that None results are not cached."""
        call_count = 0
        
        @cache_frame(ttl_seconds=60)
        async def get_value(depth: float):
            nonlocal call_count
            call_count += 1
            return None
        
        # Both calls should execute the function
        result1 = await get_value(100.0)
        result2 = await get_value(100.0)
        
        assert result1 is None
        assert result2 is None
        assert call_count == 2  # Called twice
    
    @pytest.mark.asyncio
    async def test_cache_range_decorator(self):
        """Test @cache_range decorator caches range queries."""
        call_count = 0
        
        @cache_range(ttl_seconds=60)
        async def get_range(
            depth_min: float = None,
            depth_max: float = None,
            limit: int = 100,
            offset: int = 0,
        ) -> List[str]:
            nonlocal call_count
            call_count += 1
            return [f"item_{i}" for i in range(5)]
        
        # First call - cache miss
        result1 = await get_range(depth_min=100.0, depth_max=200.0, limit=50)
        assert len(result1) == 5
        assert call_count == 1
        
        # Same parameters - cache hit
        result2 = await get_range(depth_min=100.0, depth_max=200.0, limit=50)
        assert len(result2) == 5
        assert call_count == 1  # Not called again
        
        # Different parameters - cache miss
        result3 = await get_range(depth_min=100.0, depth_max=300.0, limit=50)
        assert len(result3) == 5
        assert call_count == 2
        
        # Verify stats (use >= since cache may have entries from previous tests)
        stats = get_cache_stats()
        assert stats["range_cache"]["hits"] >= 1
        assert stats["range_cache"]["misses"] >= 2
    
    @pytest.mark.asyncio
    async def test_cache_expiration(self):
        """Test that cached values expire after TTL."""
        call_count = 0
        
        @cache_frame(ttl_seconds=0.1)  # 100ms TTL
        async def get_value(depth: float):
            nonlocal call_count
            call_count += 1
            return f"value_{depth}"
        
        # First call
        result1 = await get_value(100.0)
        assert call_count == 1
        
        # Second call immediately - cache hit
        result2 = await get_value(100.0)
        assert call_count == 1
        
        # Wait for expiration
        await asyncio.sleep(0.15)
        
        # Third call after expiration - cache miss
        result3 = await get_value(100.0)
        assert call_count == 2
    
    def test_get_cache_stats(self):
        """Test get_cache_stats returns both caches."""
        stats = get_cache_stats()
        
        assert "frame_cache" in stats
        assert "range_cache" in stats
        assert "hits" in stats["frame_cache"]
        assert "misses" in stats["frame_cache"]
        assert "size" in stats["frame_cache"]
        assert "hit_rate_percent" in stats["frame_cache"]
    
    def test_clear_all_caches(self):
        """Test clearing all caches."""
        # This is tested implicitly in the fixture, but let's be explicit
        clear_all_caches()
        
        stats = get_cache_stats()
        assert stats["frame_cache"]["size"] == 0
        assert stats["range_cache"]["size"] == 0
    
    def test_cleanup_expired_entries(self):
        """Test cleaning up expired entries from all caches."""
        # Add expired entries
        @cache_frame(ttl_seconds=0.01)
        async def get_value(depth: float):
            return f"value_{depth}"
        
        # Run in event loop
        async def populate():
            await get_value(100.0)
            await get_value(200.0)
        
        asyncio.run(populate())
        
        # Wait for expiration
        time.sleep(0.05)
        
        # Cleanup
        cleanup_expired_entries()
        
        # Stats should show expirations
        stats = get_cache_stats()
        assert stats["frame_cache"]["size"] == 0


class TestCacheIntegration:
    """Integration tests with API-like scenarios."""
    
    @pytest.fixture(autouse=True)
    def clear_caches(self):
        """Clear all caches before each test."""
        clear_all_caches()
        yield
        clear_all_caches()
    
    @pytest.mark.asyncio
    async def test_repeated_frame_lookups(self):
        """Simulate repeated API calls for same frame."""
        call_count = 0
        
        @cache_frame(ttl_seconds=60)
        async def get_frame_by_depth(depth: float):
            nonlocal call_count
            call_count += 1
            # Simulate DB query delay
            await asyncio.sleep(0.01)
            return {"depth": depth, "data": "image_data"}
        
        # Simulate 10 API calls for same frame
        start = time.time()
        for _ in range(10):
            result = await get_frame_by_depth(100.0)
            assert result["depth"] == 100.0
        elapsed = time.time() - start
        
        # Should only call function once
        assert call_count == 1
        
        # Cached calls should be much faster (< 50ms total vs 100ms without cache)
        assert elapsed < 0.05
        
        # Verify cache statistics show hits > 0
        stats = get_cache_stats()
        assert stats["frame_cache"]["hits"] >= 9
        assert stats["frame_cache"]["hit_rate_percent"] > 0
    
    @pytest.mark.asyncio
    async def test_pagination_caching(self):
        """Simulate pagination with different offsets."""
        call_count = 0
        
        @cache_range(ttl_seconds=60)
        async def get_frames_by_range(
            depth_min: float = None,
            depth_max: float = None,
            limit: int = 100,
            offset: int = 0,
        ):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return [{"depth": i} for i in range(offset, offset + limit)]
        
        # Page 1
        page1 = await get_frames_by_range(0.0, 1000.0, limit=50, offset=0)
        assert len(page1) == 50
        assert call_count == 1
        
        # Page 1 again (cached)
        page1_again = await get_frames_by_range(0.0, 1000.0, limit=50, offset=0)
        assert len(page1_again) == 50
        assert call_count == 1  # Not called again
        
        # Page 2 (different offset, cache miss)
        page2 = await get_frames_by_range(0.0, 1000.0, limit=50, offset=50)
        assert len(page2) == 50
        assert call_count == 2
        
        stats = get_cache_stats()
        assert stats["range_cache"]["hits"] >= 1
        assert stats["range_cache"]["misses"] >= 2
