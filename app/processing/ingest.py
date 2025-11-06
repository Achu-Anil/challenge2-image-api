"""
CSV data ingestion pipeline for depth-keyed image frames.

This module handles:
1. CSV exploration and validation
2. Chunked streaming ingestion to avoid memory issues
3. Batch processing with database upserts
"""

from pathlib import Path

import pandas as pd
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_logger, settings
from app.db import Frame, get_db_context
from app.processing import process_row_to_png

logger = get_logger(__name__)


def explore_csv(csv_path: str | Path) -> dict:
    """
    Quick exploration of CSV file structure without loading all data.

    Reads first few rows to determine:
    - Shape (number of rows and columns)
    - Data types
    - Column names
    - Sample values
    - Memory estimate

    Args:
        csv_path: Path to CSV file

    Returns:
        dict: Exploration summary with shape, dtypes, sample, etc.

    Example:
        >>> info = explore_csv("data/frames.csv")
        >>> print(f"Rows: {info['num_rows']}, Cols: {info['num_cols']}")
    """
    csv_path = Path(csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    # Read first few rows to inspect structure
    df_sample = pd.read_csv(csv_path, nrows=5)

    # Get full row count (fast - just counts lines)
    with open(csv_path, "r") as f:
        num_rows = sum(1 for _ in f) - 1  # Subtract header

    num_cols = len(df_sample.columns)

    # Check if first column is 'depth' or similar
    first_col = df_sample.columns[0]
    pixel_cols = df_sample.columns[1:]

    info = {
        "csv_path": str(csv_path),
        "num_rows": num_rows,
        "num_cols": num_cols,
        "first_column": first_col,
        "num_pixel_columns": len(pixel_cols),
        "dtypes": df_sample.dtypes.to_dict(),
        "sample_depths": df_sample[first_col].tolist(),
        "memory_estimate_mb": (num_rows * num_cols * 8) / (1024 * 1024),  # Rough estimate
        "file_size_mb": csv_path.stat().st_size / (1024 * 1024),
    }

    logger.info(
        "CSV exploration complete",
        extra={
            "rows": num_rows,
            "cols": num_cols,
            "pixel_cols": len(pixel_cols),
            "file_size_mb": round(info["file_size_mb"], 2),
        },
    )

    return info


def read_csv_chunks(csv_path: str | Path, chunk_size: int = 500):
    """
    Stream CSV file in chunks to avoid loading entire file into memory.

    Uses pandas chunked reading for memory efficiency.

    Args:
        csv_path: Path to CSV file
        chunk_size: Number of rows per chunk

    Yields:
        pd.DataFrame: Chunk of rows from CSV

    Example:
        for chunk in read_csv_chunks("data/frames.csv", 100):
            print(f"Processing {len(chunk)} rows")
    """
    csv_path = Path(csv_path)

    logger.info(
        "Starting CSV chunked read", extra={"csv_path": str(csv_path), "chunk_size": chunk_size}
    )

    # Use pandas chunk reader
    for chunk_num, chunk_df in enumerate(pd.read_csv(csv_path, chunksize=chunk_size), start=1):
        logger.debug(
            "Read CSV chunk",
            extra={
                "chunk_num": chunk_num,
                "rows": len(chunk_df),
                "depth_range": (float(chunk_df.iloc[:, 0].min()), float(chunk_df.iloc[:, 0].max())),
            },
        )
        yield chunk_df


async def process_chunk_to_frames(
    chunk_df: pd.DataFrame, source_width: int = 200, target_width: int = 150
) -> list[dict]:
    """
    Process a chunk of CSV rows into Frame data dictionaries.

    For each row:
    1. Extract depth value (first column)
    2. Extract pixel values (remaining columns)
    3. Process: resize + colormap + PNG encode
    4. Create Frame dict ready for DB insert

    Args:
        chunk_df: DataFrame chunk with depth + pixel columns
        source_width: Expected number of pixel columns (default 200)
        target_width: Target image width after resize (default 150)

    Returns:
        list[dict]: Frame dictionaries with depth, image_png, width, height

    Raises:
        ValueError: If pixel column count doesn't match source_width
    """
    frames = []

    # Get column names
    depth_col = chunk_df.columns[0]
    pixel_cols = chunk_df.columns[1:]

    if len(pixel_cols) != source_width:
        raise ValueError(f"Expected {source_width} pixel columns, got {len(pixel_cols)}")

    # Process each row
    for idx, row in chunk_df.iterrows():
        try:
            # Extract depth and pixel values
            depth = float(row[depth_col])
            pixel_values = row[pixel_cols].values

            # Process to PNG
            png_bytes, width, height = process_row_to_png(
                pixel_values, source_width=source_width, target_width=target_width
            )

            # Create Frame dict
            frame_data = {
                "depth": depth,
                "image_png": png_bytes,
                "width": width,
                "height": height,
            }

            frames.append(frame_data)

        except Exception as e:
            logger.error(
                "Failed to process row",
                extra={
                    "row_index": idx,
                    "depth": float(row[depth_col]) if depth_col in row else None,
                    "error": str(e),
                },
                exc_info=True,
            )
            # Continue processing other rows
            continue

    logger.info(
        "Processed chunk",
        extra={"rows_processed": len(frames), "rows_failed": len(chunk_df) - len(frames)},
    )

    return frames


async def upsert_frames(db: AsyncSession, frames: list[dict]) -> int:
    """
    Upsert frames into database (insert or update on conflict).

    Uses SQLite's INSERT OR REPLACE or PostgreSQL's ON CONFLICT
    to ensure idempotent ingestion.

    Args:
        db: Async database session
        frames: List of frame dictionaries

    Returns:
        int: Number of frames upserted
    """
    if not frames:
        return 0

    # Use SQLite upsert (INSERT OR REPLACE)
    stmt = sqlite_insert(Frame).values(frames)
    stmt = stmt.on_conflict_do_update(
        index_elements=["depth"],
        set_={
            "image_png": stmt.excluded.image_png,
            "width": stmt.excluded.width,
            "height": stmt.excluded.height,
            "updated_at": stmt.excluded.updated_at,
        },
    )

    await db.execute(stmt)
    await db.commit()

    logger.info("Upserted frames to database", extra={"count": len(frames)})

    return len(frames)


async def ingest_csv(
    csv_path: str | Path | None = None,
    chunk_size: int | None = None,
    source_width: int = 200,
    target_width: int = 150,
) -> dict:
    """
    Complete CSV ingestion pipeline with chunked processing.

    Steps:
    1. Explore CSV to validate structure
    2. Stream CSV in chunks
    3. Process each chunk: resize + colormap + encode
    4. Upsert frames to database in batches

    Args:
        csv_path: Path to CSV file (default from settings)
        chunk_size: Rows per chunk (default from settings)
        source_width: Expected pixel columns (default 200)
        target_width: Target image width (default 150)

    Returns:
        dict: Ingestion summary with stats including performance metrics

    Example:
        >>> result = await ingest_csv("data/frames.csv", chunk_size=100)
        >>> print(f"Processed {result['rows_processed']} rows in {result['duration_seconds']:.2f}s")
        >>> print(f"Throughput: {result['rows_per_second']:.0f} rows/sec")
    """
    import time

    start_time = time.time()

    # Use settings defaults if not provided
    csv_path = Path(csv_path or settings.csv_file_path)
    chunk_size = chunk_size or settings.chunk_size

    logger.info(
        "Starting CSV ingestion",
        extra={
            "csv_path": str(csv_path),
            "chunk_size": chunk_size,
            "source_width": source_width,
            "target_width": target_width,
        },
    )

    # Step 1: Explore CSV
    csv_info = explore_csv(csv_path)

    # Validate pixel columns
    expected_cols = source_width + 1  # depth + pixels
    if csv_info["num_cols"] != expected_cols:
        raise ValueError(
            f"Expected {expected_cols} columns (1 depth + {source_width} pixels), "
            f"got {csv_info['num_cols']}"
        )

    # Step 2: Process chunks with performance tracking
    total_rows = 0
    total_frames = 0
    chunk_count = 0

    async with get_db_context() as db:
        for chunk_df in read_csv_chunks(csv_path, chunk_size):
            chunk_count += 1
            time.time()

            # Process chunk to frames
            frames = await process_chunk_to_frames(
                chunk_df, source_width=source_width, target_width=target_width
            )

            # Upsert to database
            upserted = await upsert_frames(db, frames)

            total_rows += len(chunk_df)
            total_frames += upserted

            # Log progress periodically (every 10 chunks)
            if chunk_count % 10 == 0:
                elapsed = time.time() - start_time
                rows_per_sec = total_rows / elapsed if elapsed > 0 else 0
                logger.info(
                    f"Ingestion progress: {total_rows} rows processed",
                    extra={
                        "rows_processed": total_rows,
                        "chunks_processed": chunk_count,
                        "rows_per_second": round(rows_per_sec, 1),
                        "elapsed_seconds": round(elapsed, 2),
                    },
                )

    # Calculate final metrics
    duration = time.time() - start_time
    rows_per_second = total_rows / duration if duration > 0 else 0

    result = {
        "csv_path": str(csv_path),
        "rows_processed": total_rows,
        "frames_upserted": total_frames,
        "chunk_size": chunk_size,
        "chunks_processed": chunk_count,
        "source_width": source_width,
        "target_width": target_width,
        "duration_seconds": round(duration, 2),
        "rows_per_second": round(rows_per_second, 1),
    }

    logger.info("CSV ingestion complete", extra=result)

    return result
