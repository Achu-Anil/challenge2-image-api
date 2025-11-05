"""
Database operations for frame storage and retrieval.

This module provides high-level database operations with proper transaction
management, error handling, and performance optimizations.
"""

from typing import Optional, Sequence

from sqlalchemy import select, func, and_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_logger
from app.db.models import Frame

logger = get_logger(__name__)


async def upsert_frame(
    session: AsyncSession,
    depth: float,
    width: int,
    height: int,
    png_bytes: bytes,
) -> Frame:
    """
    Insert or update a single frame (idempotent operation).
    
    Uses SQLite's INSERT OR REPLACE or PostgreSQL's ON CONFLICT to handle
    duplicate depths gracefully. If a frame with the same depth exists,
    it will be updated with new data.
    
    **Transaction Management:**
    - Does NOT commit - caller controls transaction boundary
    - Use with batch operations for better performance
    
    Args:
        session: Async database session
        depth: Depth value (primary key)
        width: Image width in pixels
        height: Image height in pixels
        png_bytes: PNG-encoded image binary data
    
    Returns:
        Frame: The created or updated Frame object
    
    Example:
        >>> async with get_db_context() as db:
        ...     frame = await upsert_frame(db, 100.5, 150, 1, png_data)
        ...     await db.commit()  # Explicit commit
    """
    # Build upsert statement
    stmt = sqlite_insert(Frame).values(
        depth=depth,
        width=width,
        height=height,
        image_png=png_bytes,
    )
    
    # On conflict, update all fields except created_at
    stmt = stmt.on_conflict_do_update(
        index_elements=["depth"],
        set_={
            "image_png": stmt.excluded.image_png,
            "width": stmt.excluded.width,
            "height": stmt.excluded.height,
            "updated_at": func.now(),  # Manually set updated_at timestamp
        },
    )
    
    await session.execute(stmt)
    
    # Flush to database to ensure upsert is executed
    await session.flush()
    
    # Fetch the frame (after upsert and flush)
    result = await session.execute(
        select(Frame).where(Frame.depth == depth)
    )
    frame = result.scalar_one()
    
    # Refresh from database to get latest values
    await session.refresh(frame)
    
    logger.debug(
        "Upserted frame",
        extra={
            "depth": depth,
            "width": width,
            "height": height,
            "size_bytes": len(png_bytes),
        }
    )
    
    return frame


async def upsert_frames_batch(
    session: AsyncSession,
    frames: list[dict],
) -> int:
    """
    Upsert multiple frames in a single batch operation.
    
    More efficient than individual upserts for bulk loading.
    Uses batch INSERT with ON CONFLICT for optimal performance.
    
    **Transaction Management:**
    - Does NOT commit - caller controls transaction boundary
    - Recommended: commit per batch (e.g., every 500 frames)
    
    Args:
        session: Async database session
        frames: List of frame dicts with keys: depth, width, height, image_png
    
    Returns:
        int: Number of frames upserted
    
    Example:
        >>> frames = [
        ...     {"depth": 100.5, "width": 150, "height": 1, "image_png": data1},
        ...     {"depth": 101.0, "width": 150, "height": 1, "image_png": data2},
        ... ]
        >>> async with get_db_context() as db:
        ...     count = await upsert_frames_batch(db, frames)
        ...     await db.commit()
    """
    if not frames:
        return 0
    
    # Build batch upsert statement
    stmt = sqlite_insert(Frame).values(frames)
    stmt = stmt.on_conflict_do_update(
        index_elements=["depth"],
        set_={
            "image_png": stmt.excluded.image_png,
            "width": stmt.excluded.width,
            "height": stmt.excluded.height,
            "updated_at": func.now(),  # Manually set updated_at timestamp
        },
    )
    
    await session.execute(stmt)
    
    logger.info(
        "Upserted frame batch",
        extra={"count": len(frames)}
    )
    
    return len(frames)


async def get_frame_by_depth(
    session: AsyncSession,
    depth: float,
) -> Optional[Frame]:
    """
    Retrieve a single frame by depth value.
    
    Args:
        session: Async database session
        depth: Depth value to search for
    
    Returns:
        Frame object if found, None otherwise
    
    Example:
        >>> async with get_db_context() as db:
        ...     frame = await get_frame_by_depth(db, 100.5)
        ...     if frame:
        ...         print(f"Found frame at depth {frame.depth}")
    """
    result = await session.execute(
        select(Frame).where(Frame.depth == depth)
    )
    return result.scalar_one_or_none()


async def get_frames_by_depth_range(
    session: AsyncSession,
    depth_min: Optional[float] = None,
    depth_max: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[Frame]:
    """
    Retrieve frames within a depth range with pagination.
    
    Efficient query using indexed depth column (primary key).
    Sorted by depth ascending for consistent ordering.
    
    Args:
        session: Async database session
        depth_min: Minimum depth (inclusive), None = no lower bound
        depth_max: Maximum depth (inclusive), None = no upper bound
        limit: Maximum number of frames to return
        offset: Number of frames to skip (for pagination)
    
    Returns:
        List of Frame objects matching criteria
    
    Example:
        >>> async with get_db_context() as db:
        ...     # Get frames between depth 100 and 200
        ...     frames = await get_frames_by_depth_range(db, 100.0, 200.0, limit=50)
        ...     print(f"Found {len(frames)} frames")
    """
    # Build query with optional depth filters
    conditions = []
    if depth_min is not None:
        conditions.append(Frame.depth >= depth_min)
    if depth_max is not None:
        conditions.append(Frame.depth <= depth_max)
    
    query = select(Frame)
    if conditions:
        query = query.where(and_(*conditions))
    
    # Add ordering and pagination
    query = query.order_by(Frame.depth).limit(limit).offset(offset)
    
    result = await session.execute(query)
    frames = result.scalars().all()
    
    logger.debug(
        "Retrieved frames by depth range",
        extra={
            "depth_min": depth_min,
            "depth_max": depth_max,
            "limit": limit,
            "offset": offset,
            "count": len(frames),
        }
    )
    
    return frames


async def count_frames(
    session: AsyncSession,
    depth_min: Optional[float] = None,
    depth_max: Optional[float] = None,
) -> int:
    """
    Count frames within optional depth range.
    
    Efficient count query for pagination metadata.
    
    Args:
        session: Async database session
        depth_min: Minimum depth (inclusive), None = no lower bound
        depth_max: Maximum depth (inclusive), None = no upper bound
    
    Returns:
        Total number of frames matching criteria
    
    Example:
        >>> async with get_db_context() as db:
        ...     total = await count_frames(db, depth_min=100.0, depth_max=200.0)
        ...     print(f"Total frames in range: {total}")
    """
    # Build query with optional depth filters
    conditions = []
    if depth_min is not None:
        conditions.append(Frame.depth >= depth_min)
    if depth_max is not None:
        conditions.append(Frame.depth <= depth_max)
    
    query = select(func.count()).select_from(Frame)
    if conditions:
        query = query.where(and_(*conditions))
    
    result = await session.execute(query)
    count = result.scalar_one()
    
    return count


async def delete_frame(
    session: AsyncSession,
    depth: float,
) -> bool:
    """
    Delete a frame by depth value.
    
    Args:
        session: Async database session
        depth: Depth value of frame to delete
    
    Returns:
        True if frame was deleted, False if not found
    
    Example:
        >>> async with get_db_context() as db:
        ...     deleted = await delete_frame(db, 100.5)
        ...     if deleted:
        ...         await db.commit()
    """
    frame = await get_frame_by_depth(session, depth)
    if frame is None:
        return False
    
    await session.delete(frame)
    logger.info("Deleted frame", extra={"depth": depth})
    
    return True


async def get_depth_range(
    session: AsyncSession,
) -> tuple[Optional[float], Optional[float]]:
    """
    Get minimum and maximum depth values in database.
    
    Useful for API metadata and validation.
    
    Args:
        session: Async database session
    
    Returns:
        Tuple of (min_depth, max_depth), or (None, None) if no frames
    
    Example:
        >>> async with get_db_context() as db:
        ...     min_d, max_d = await get_depth_range(db)
        ...     print(f"Depth range: {min_d} to {max_d}")
    """
    result = await session.execute(
        select(
            func.min(Frame.depth),
            func.max(Frame.depth)
        )
    )
    min_depth, max_depth = result.one()
    
    return min_depth, max_depth
