"""
Comprehensive tests for database operations.

Tests cover:
- Single frame upsert (insert and update)
- Batch upsert operations
- Query operations (by depth, range, count)
- Transaction management
- Idempotency
- Performance benchmarks
"""

import time

import numpy as np
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import (
    Frame,
    count_frames,
    delete_frame,
    get_db_context,
    get_depth_range,
    get_frame_by_depth,
    get_frames_by_depth_range,
    init_db,
    upsert_frame,
    upsert_frames_batch,
)

# Test fixtures


@pytest.fixture(scope="function")
async def db_session():
    """Provide a clean database session for each test."""
    from sqlalchemy import delete

    # Initialize database tables
    await init_db()

    # Provide session
    async with get_db_context() as session:
        # Delete all existing frames before test
        await session.execute(delete(Frame))
        await session.commit()

        yield session

        # Clean up after test
        await session.rollback()
        await session.execute(delete(Frame))
        await session.commit()


@pytest.fixture
def sample_png_bytes() -> bytes:
    """Generate sample PNG bytes for testing."""
    # Simple 1x1 PNG (smallest valid PNG)
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


# Single frame operations


class TestUpsertFrame:
    """Tests for upsert_frame() function."""

    async def test_insert_new_frame(self, db_session: AsyncSession, sample_png_bytes: bytes):
        """Test inserting a new frame."""
        depth = 100.5
        frame = await upsert_frame(
            db_session, depth=depth, width=150, height=1, png_bytes=sample_png_bytes
        )
        await db_session.commit()

        assert frame.depth == depth
        assert frame.width == 150
        assert frame.height == 1
        assert frame.image_png == sample_png_bytes
        assert frame.created_at is not None

    async def test_update_existing_frame(self, db_session: AsyncSession, sample_png_bytes: bytes):
        """Test updating an existing frame (upsert on conflict)."""
        depth = 100.5

        # Insert initial frame
        frame1 = await upsert_frame(
            db_session, depth=depth, width=150, height=1, png_bytes=sample_png_bytes
        )
        await db_session.commit()
        created_at = frame1.created_at

        # Update with new data
        new_png = sample_png_bytes + b"\x00\x00"  # Different data
        frame2 = await upsert_frame(db_session, depth=depth, width=200, height=2, png_bytes=new_png)
        await db_session.commit()

        # Should be same frame (updated)
        assert frame2.depth == depth
        assert frame2.width == 200
        assert frame2.height == 2
        assert frame2.image_png == new_png
        assert frame2.created_at == created_at  # Created time unchanged
        assert frame2.updated_at is not None  # Updated time set

    async def test_idempotent_upsert(self, db_session: AsyncSession, sample_png_bytes: bytes):
        """Test that upserting same data multiple times is idempotent."""
        depth = 100.5

        # Insert 3 times with same data
        frame = None
        for _ in range(3):
            frame = await upsert_frame(
                db_session, depth=depth, width=150, height=1, png_bytes=sample_png_bytes
            )
            await db_session.commit()

        # Should have only one frame
        total = await count_frames(db_session)
        assert total == 1
        assert frame is not None
        assert frame.depth == depth


class TestBatchOperations:
    """Tests for batch upsert operations."""

    async def test_batch_upsert_empty_list(self, db_session: AsyncSession):
        """Test batch upsert with empty list."""
        count = await upsert_frames_batch(db_session, [])
        await db_session.commit()

        assert count == 0

    async def test_batch_upsert_multiple_frames(
        self, db_session: AsyncSession, sample_png_bytes: bytes
    ):
        """Test batch upserting multiple frames."""
        frames = [
            {"depth": 100.0, "width": 150, "height": 1, "image_png": sample_png_bytes},
            {"depth": 101.0, "width": 150, "height": 1, "image_png": sample_png_bytes},
            {"depth": 102.0, "width": 150, "height": 1, "image_png": sample_png_bytes},
        ]

        count = await upsert_frames_batch(db_session, frames)
        await db_session.commit()

        assert count == 3

        # Verify all frames exist
        total = await count_frames(db_session)
        assert total == 3

    async def test_batch_upsert_with_duplicates(
        self, db_session: AsyncSession, sample_png_bytes: bytes
    ):
        """Test batch upsert handles duplicates correctly."""
        # First batch
        frames1 = [
            {"depth": 100.0, "width": 150, "height": 1, "image_png": sample_png_bytes},
            {"depth": 101.0, "width": 150, "height": 1, "image_png": sample_png_bytes},
        ]
        await upsert_frames_batch(db_session, frames1)
        await db_session.commit()

        # Second batch with overlapping depth
        new_png = sample_png_bytes + b"\x00"
        frames2 = [
            {"depth": 101.0, "width": 200, "height": 2, "image_png": new_png},
            {"depth": 102.0, "width": 150, "height": 1, "image_png": sample_png_bytes},
        ]
        await upsert_frames_batch(db_session, frames2)
        await db_session.commit()

        # Should have 3 unique frames
        total = await count_frames(db_session)
        assert total == 3

        # Verify depth 101.0 was updated
        frame_101 = await get_frame_by_depth(db_session, 101.0)
        assert frame_101 is not None
        assert frame_101.width == 200
        assert frame_101.height == 2
        assert frame_101.image_png == new_png


# Query operations


class TestGetFrameByDepth:
    """Tests for retrieving single frames."""

    async def test_get_existing_frame(self, db_session: AsyncSession, sample_png_bytes: bytes):
        """Test retrieving an existing frame."""
        depth = 100.5
        await upsert_frame(db_session, depth, 150, 1, sample_png_bytes)
        await db_session.commit()

        frame = await get_frame_by_depth(db_session, depth)

        assert frame is not None
        assert frame.depth == depth

    async def test_get_nonexistent_frame(self, db_session: AsyncSession):
        """Test retrieving a non-existent frame returns None."""
        frame = await get_frame_by_depth(db_session, 999.9)
        assert frame is None


class TestGetFramesByDepthRange:
    """Tests for range queries."""

    async def test_range_query_with_bounds(self, db_session: AsyncSession, sample_png_bytes: bytes):
        """Test querying frames within depth range."""
        # Insert frames at depths 100, 150, 200, 250, 300
        for depth in [100.0, 150.0, 200.0, 250.0, 300.0]:
            await upsert_frame(db_session, depth, 150, 1, sample_png_bytes)
        await db_session.commit()

        # Query range 150-250 (inclusive)
        frames = await get_frames_by_depth_range(db_session, depth_min=150.0, depth_max=250.0)

        assert len(frames) == 3
        assert [f.depth for f in frames] == [150.0, 200.0, 250.0]

    async def test_range_query_no_lower_bound(
        self, db_session: AsyncSession, sample_png_bytes: bytes
    ):
        """Test query with only upper bound."""
        for depth in [100.0, 150.0, 200.0]:
            await upsert_frame(db_session, depth, 150, 1, sample_png_bytes)
        await db_session.commit()

        frames = await get_frames_by_depth_range(db_session, depth_max=150.0)

        assert len(frames) == 2
        assert [f.depth for f in frames] == [100.0, 150.0]

    async def test_range_query_no_upper_bound(
        self, db_session: AsyncSession, sample_png_bytes: bytes
    ):
        """Test query with only lower bound."""
        for depth in [100.0, 150.0, 200.0]:
            await upsert_frame(db_session, depth, 150, 1, sample_png_bytes)
        await db_session.commit()

        frames = await get_frames_by_depth_range(db_session, depth_min=150.0)

        assert len(frames) == 2
        assert [f.depth for f in frames] == [150.0, 200.0]

    async def test_range_query_no_bounds(self, db_session: AsyncSession, sample_png_bytes: bytes):
        """Test query with no bounds returns all frames."""
        for depth in [100.0, 150.0, 200.0]:
            await upsert_frame(db_session, depth, 150, 1, sample_png_bytes)
        await db_session.commit()

        frames = await get_frames_by_depth_range(db_session)

        assert len(frames) == 3

    async def test_range_query_with_limit(self, db_session: AsyncSession, sample_png_bytes: bytes):
        """Test pagination with limit."""
        for depth in range(100, 110):
            await upsert_frame(db_session, float(depth), 150, 1, sample_png_bytes)
        await db_session.commit()

        frames = await get_frames_by_depth_range(db_session, limit=5)

        assert len(frames) == 5

    async def test_range_query_with_offset(self, db_session: AsyncSession, sample_png_bytes: bytes):
        """Test pagination with offset."""
        for depth in [100.0, 150.0, 200.0, 250.0, 300.0]:
            await upsert_frame(db_session, depth, 150, 1, sample_png_bytes)
        await db_session.commit()

        # Skip first 2, get next 2
        frames = await get_frames_by_depth_range(db_session, limit=2, offset=2)

        assert len(frames) == 2
        assert [f.depth for f in frames] == [200.0, 250.0]

    async def test_range_query_sorted_by_depth(
        self, db_session: AsyncSession, sample_png_bytes: bytes
    ):
        """Test that results are sorted by depth ascending."""
        # Clear cache to avoid detached instance issues
        from app.core import clear_all_caches

        clear_all_caches()

        # Insert in random order
        for depth in [300.0, 100.0, 200.0, 150.0]:
            await upsert_frame(db_session, depth, 150, 1, sample_png_bytes)
        await db_session.commit()

        frames = await get_frames_by_depth_range(db_session)

        assert [f.depth for f in frames] == [100.0, 150.0, 200.0, 300.0]


class TestCountFrames:
    """Tests for count_frames() function."""

    async def test_count_empty_database(self, db_session: AsyncSession):
        """Test counting frames in empty database."""
        count = await count_frames(db_session)
        assert count == 0

    async def test_count_all_frames(self, db_session: AsyncSession, sample_png_bytes: bytes):
        """Test counting all frames."""
        for depth in [100.0, 150.0, 200.0]:
            await upsert_frame(db_session, depth, 150, 1, sample_png_bytes)
        await db_session.commit()

        count = await count_frames(db_session)
        assert count == 3

    async def test_count_frames_in_range(self, db_session: AsyncSession, sample_png_bytes: bytes):
        """Test counting frames within depth range."""
        for depth in [100.0, 150.0, 200.0, 250.0, 300.0]:
            await upsert_frame(db_session, depth, 150, 1, sample_png_bytes)
        await db_session.commit()

        count = await count_frames(db_session, depth_min=150.0, depth_max=250.0)
        assert count == 3


class TestDeleteFrame:
    """Tests for frame deletion."""

    async def test_delete_existing_frame(self, db_session: AsyncSession, sample_png_bytes: bytes):
        """Test deleting an existing frame."""
        from app.core import clear_all_caches

        depth = 100.5
        await upsert_frame(db_session, depth, 150, 1, sample_png_bytes)
        await db_session.commit()

        deleted = await delete_frame(db_session, depth)
        await db_session.commit()

        assert deleted is True

        # Clear cache to get fresh data after deletion
        clear_all_caches()

        # Verify frame is gone
        frame = await get_frame_by_depth(db_session, depth)
        assert frame is None

    async def test_delete_nonexistent_frame(self, db_session: AsyncSession):
        """Test deleting a non-existent frame."""
        deleted = await delete_frame(db_session, 999.9)
        assert deleted is False


class TestGetDepthRange:
    """Tests for get_depth_range() function."""

    async def test_depth_range_empty_database(self, db_session: AsyncSession):
        """Test getting depth range from empty database."""
        min_d, max_d = await get_depth_range(db_session)
        assert min_d is None
        assert max_d is None

    async def test_depth_range_single_frame(
        self, db_session: AsyncSession, sample_png_bytes: bytes
    ):
        """Test depth range with single frame."""
        await upsert_frame(db_session, 100.5, 150, 1, sample_png_bytes)
        await db_session.commit()

        min_d, max_d = await get_depth_range(db_session)
        assert min_d == 100.5
        assert max_d == 100.5

    async def test_depth_range_multiple_frames(
        self, db_session: AsyncSession, sample_png_bytes: bytes
    ):
        """Test depth range with multiple frames."""
        for depth in [100.0, 250.0, 150.0, 300.0, 200.0]:
            await upsert_frame(db_session, depth, 150, 1, sample_png_bytes)
        await db_session.commit()

        min_d, max_d = await get_depth_range(db_session)
        assert min_d == 100.0
        assert max_d == 300.0


# Performance tests


class TestPerformance:
    """Performance benchmarks for database operations."""

    async def test_batch_upsert_1000_frames(
        self, db_session: AsyncSession, sample_png_bytes: bytes
    ):
        """Benchmark: Upsert 1000 frames in batches."""
        # Generate 1000 frames
        frames = [
            {"depth": float(i), "width": 150, "height": 1, "image_png": sample_png_bytes}
            for i in range(1000)
        ]

        # Batch upsert
        start = time.perf_counter()
        count = await upsert_frames_batch(db_session, frames)
        await db_session.commit()
        elapsed = time.perf_counter() - start

        print(f"\n✅ Upserted {count} frames in {elapsed:.3f}s")
        print(f"   Per-frame time: {elapsed/count*1000:.2f}ms")

        assert count == 1000
        assert elapsed < 5.0  # Should complete in <5 seconds

    async def test_query_performance_large_dataset(
        self, db_session: AsyncSession, sample_png_bytes: bytes
    ):
        """Benchmark: Query performance with 1000 frames."""
        # Insert 1000 frames
        frames = [
            {"depth": float(i), "width": 150, "height": 1, "image_png": sample_png_bytes}
            for i in range(1000)
        ]
        await upsert_frames_batch(db_session, frames)
        await db_session.commit()

        # Benchmark range query
        start = time.perf_counter()
        result = await get_frames_by_depth_range(
            db_session,
            depth_min=400.0,
            depth_max=600.0,
            limit=250,  # Need to override default limit of 100
        )
        elapsed = time.perf_counter() - start

        print(f"\n✅ Range query returned {len(result)} frames in {elapsed*1000:.2f}ms")

        assert len(result) == 201  # 400-600 inclusive
        assert elapsed < 0.1  # Should complete in <100ms

    async def test_count_performance_large_dataset(
        self, db_session: AsyncSession, sample_png_bytes: bytes
    ):
        """Benchmark: Count query performance."""
        # Insert 1000 frames
        frames = [
            {"depth": float(i), "width": 150, "height": 1, "image_png": sample_png_bytes}
            for i in range(1000)
        ]
        await upsert_frames_batch(db_session, frames)
        await db_session.commit()

        # Benchmark count
        start = time.perf_counter()
        count = await count_frames(db_session, depth_min=400.0, depth_max=600.0)
        elapsed = time.perf_counter() - start

        print(f"\n✅ Count query completed in {elapsed*1000:.2f}ms")

        assert count == 201
        assert elapsed < 0.05  # Should complete in <50ms


# Integration tests


class TestTransactionManagement:
    """Tests for transaction handling."""

    async def test_commit_per_batch(self, db_session: AsyncSession, sample_png_bytes: bytes):
        """Test committing after batch operations."""
        # Batch 1
        frames1 = [
            {"depth": float(i), "width": 150, "height": 1, "image_png": sample_png_bytes}
            for i in range(100, 200)
        ]
        await upsert_frames_batch(db_session, frames1)
        await db_session.commit()

        # Batch 2
        frames2 = [
            {"depth": float(i), "width": 150, "height": 1, "image_png": sample_png_bytes}
            for i in range(200, 300)
        ]
        await upsert_frames_batch(db_session, frames2)
        await db_session.commit()

        # Verify all frames exist
        total = await count_frames(db_session)
        assert total == 200

    async def test_rollback_on_error(self, db_session: AsyncSession, sample_png_bytes: bytes):
        """Test that transactions rollback on error."""
        # Insert valid frame
        await upsert_frame(db_session, 100.0, 150, 1, sample_png_bytes)

        # Explicitly rollback to simulate error condition
        await db_session.rollback()

        # Verify nothing was committed after rollback
        count = await count_frames(db_session)
        assert count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
