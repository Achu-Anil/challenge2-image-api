"""
Ingestion script to load CSV data into the database.

This script provides a repeatable, idempotent pipeline to build/rebuild the database
from CSV data. Features include:
- Progress tracking with real-time updates every N frames
- Detailed timing and throughput metrics (frames/sec, MB/sec)
- Configurable chunk size for memory control
- Optional colored vs grayscale image storage
- Idempotent upsert (safe to re-run without duplicates)
- Comprehensive error handling with specific exit codes
- Data consistency validation

Usage:
    python -m scripts.ingest [csv_path] [options]

Examples:
    # Basic ingestion with colored images
    python -m scripts.ingest data/frames.csv

    # Smaller chunks for memory-constrained environments
    python -m scripts.ingest data/frames.csv --chunk-size 100

    # Store grayscale only (faster, smaller DB)
    python -m scripts.ingest data/frames.csv --no-store-colored

Exit Codes:
    0: Success
    1: File or configuration error
    2: Data validation error
    3: Database or unexpected error
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

from app.core import get_logger, settings, setup_logging
from app.db import get_db_context
from app.db.operations import count_frames, get_depth_range, upsert_frames_batch
from app.processing.ingest import explore_csv, process_chunk_to_frames, read_csv_chunks

logger = get_logger(__name__)


async def ingest_with_progress(
    csv_path: Path,
    chunk_size: int,
    source_width: int,
    target_width: int,
    store_colored: bool,
    progress_interval: int = 100,
) -> dict:
    """
    Ingest CSV with detailed progress tracking, timing, and validation.

    Args:
        csv_path: Path to CSV file with depth + pixel columns
        chunk_size: Number of rows to process per batch
        source_width: Expected number of pixel columns (e.g., 200)
        target_width: Target width after resize (e.g., 150)
        store_colored: If True, apply colormap; if False, store grayscale
        progress_interval: Log progress every N frames

    Returns:
        dict with keys:
            - rows_processed: Total rows read from CSV
            - frames_stored: Frames successfully stored
            - db_count: Final count from database
            - duration_seconds: Total elapsed time
            - throughput_fps: Frames per second
            - throughput_mbps: Megabytes per second (rough estimate)
            - db_size_mb: Estimated database size
            - validation_passed: True if db_count matches frames_stored
            - depth_range: Min/max depth values
            - timings: Breakdown of phase durations

    Raises:
        FileNotFoundError: CSV file doesn't exist
        ValueError: Invalid CSV structure or parameters
        Exception: Database or processing errors
    """
    start_time = time.time()
    timings = {}

    # Phase 1: Explore CSV structure
    logger.info(f"Phase 1: Exploring CSV structure at {csv_path}")
    explore_start = time.time()

    try:
        metadata = explore_csv(str(csv_path))
    except Exception as e:
        logger.error(f"Failed to explore CSV: {e}")
        raise

    timings["explore_seconds"] = time.time() - explore_start

    logger.info(
        f"CSV metadata: {metadata['num_rows']:,} rows, "
        f"{metadata['num_cols']} columns, "
        f"{metadata['file_size_mb']:.2f} MB"
    )

    if metadata["num_rows"] == 0:
        raise ValueError("CSV file is empty")

    # Phase 2: Process chunks with progress tracking
    logger.info(f"Phase 2: Processing chunks (size={chunk_size}, " f"colored={store_colored})...")
    process_start = time.time()

    total_rows = 0
    total_frames = 0
    last_progress_time = time.time()
    last_progress_frames = 0

    try:
        async with get_db_context() as session:
            for chunk_idx, chunk_df in enumerate(
                read_csv_chunks(str(csv_path), chunk_size), start=1
            ):
                chunk_start = time.time()

                # Process chunk to frame dictionaries
                # Note: store_colored parameter would be passed here if supported
                # For now, process_chunk_to_frames always creates colored images
                frames_data = await process_chunk_to_frames(
                    chunk_df,
                    source_width=source_width,
                    target_width=target_width,
                )

                # Batch upsert (idempotent - safe to re-run)
                await upsert_frames_batch(session, frames_data)
                await session.commit()

                chunk_duration = time.time() - chunk_start
                total_rows += len(chunk_df)
                total_frames += len(frames_data)

                # Progress logging every N frames or every 2 seconds
                current_time = time.time()
                frames_since_last = total_frames - last_progress_frames

                should_log = (
                    frames_since_last >= progress_interval
                    or current_time - last_progress_time >= 2.0
                    or total_rows >= metadata["num_rows"]  # Always log last chunk
                )

                if should_log:
                    elapsed = current_time - process_start
                    fps = total_frames / elapsed if elapsed > 0 else 0
                    percent = 100 * total_rows / metadata["num_rows"]

                    logger.info(
                        f"Progress: {total_rows:,}/{metadata['num_rows']:,} rows "
                        f"({percent:.1f}%), "
                        f"{total_frames:,} frames, "
                        f"{fps:.1f} fps, "
                        f"chunk #{chunk_idx} ({len(chunk_df)} rows) "
                        f"took {chunk_duration:.2f}s"
                    )
                    last_progress_time = current_time
                    last_progress_frames = total_frames

    except Exception as e:
        logger.error(f"Error during chunk processing: {e}")
        raise

    timings["process_seconds"] = time.time() - process_start

    # Phase 3: Validation
    logger.info("Phase 3: Validating ingestion results...")
    validate_start = time.time()

    try:
        async with get_db_context() as session:
            db_count = await count_frames(session)
            min_depth, max_depth = await get_depth_range(session)
    except Exception as e:
        logger.error(f"Error during validation: {e}")
        raise

    validation_passed = db_count == total_frames
    timings["validate_seconds"] = time.time() - validate_start

    if not validation_passed:
        logger.error(
            f"Validation FAILED: Stored {total_frames} frames " f"but DB contains {db_count} frames"
        )

    # Phase 4: Calculate final metrics
    total_duration = time.time() - start_time
    throughput_fps = total_frames / total_duration if total_duration > 0 else 0

    # Rough throughput estimate: assume ~10KB per 150px colored PNG
    bytes_per_frame = 10 * 1024
    throughput_mbps = (
        (total_frames * bytes_per_frame / (1024 * 1024)) / total_duration
        if total_duration > 0
        else 0
    )

    # Estimate DB size (rough: 10KB per frame + overhead)
    db_size_mb = (db_count * bytes_per_frame / (1024 * 1024)) if db_count > 0 else 0

    return {
        "rows_processed": total_rows,
        "frames_stored": total_frames,
        "db_count": db_count,
        "duration_seconds": total_duration,
        "throughput_fps": throughput_fps,
        "throughput_mbps": throughput_mbps,
        "db_size_mb": db_size_mb,
        "validation_passed": validation_passed,
        "min_depth": min_depth,
        "max_depth": max_depth,
        "timings": timings,
    }


async def main():
    """Main entry point for the ingestion script."""
    parser = argparse.ArgumentParser(
        description="Ingest CSV data into frames database with progress tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic ingestion with colored images
  python -m scripts.ingest data/frames.csv

  # Smaller chunks for memory-constrained environments
  python -m scripts.ingest data/frames.csv --chunk-size 100

  # Store grayscale only (faster, smaller DB) [NOT YET IMPLEMENTED]
  python -m scripts.ingest data/frames.csv --no-store-colored

  # Custom image dimensions
  python -m scripts.ingest data/frames.csv --source-width 200 --target-width 150

  # More frequent progress updates
  python -m scripts.ingest data/frames.csv --progress-interval 50

Exit Codes:
  0 = Success
  1 = File or configuration error
  2 = Data validation error
  3 = Database or unexpected error
        """,
    )

    parser.add_argument(
        "csv_path",
        type=str,
        help="Path to the CSV file to ingest (depth + pixel columns)",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Number of rows to process in each chunk (default: 500)",
    )

    parser.add_argument(
        "--source-width",
        type=int,
        default=200,
        help="Expected width of source images in pixels (default: 200)",
    )

    parser.add_argument(
        "--target-width",
        type=int,
        default=150,
        help="Target width to resize images to (default: 150)",
    )

    parser.add_argument(
        "--store-colored",
        action="store_true",
        default=True,
        help="Store colored images (default: True) [NOT YET IMPLEMENTED]",
    )

    parser.add_argument(
        "--no-store-colored",
        action="store_false",
        dest="store_colored",
        help="Store grayscale images only [NOT YET IMPLEMENTED]",
    )

    parser.add_argument(
        "--progress-interval",
        type=int,
        default=100,
        help="Log progress every N frames (default: 100)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Setup logging with specified level
    setup_logging(log_level=args.log_level)

    # Convert CSV path to absolute path
    csv_path = Path(args.csv_path).resolve()

    # Display configuration banner
    print(f"\n{'='*70}")
    print("CSV INGESTION CONFIGURATION")
    print(f"{'='*70}")
    print(f"CSV Path:          {csv_path}")
    print(f"Chunk Size:        {args.chunk_size:,} rows")
    print(f"Source Width:      {args.source_width} pixels")
    print(f"Target Width:      {args.target_width} pixels")
    print(f"Store Colored:     {args.store_colored} (always colored for now)")
    print(f"Progress Interval: {args.progress_interval} frames")
    print(f"Log Level:         {args.log_level}")
    print(f"Database:          {settings.database_url}")
    print(f"{'='*70}\n")

    try:
        # Pre-flight validation
        if not csv_path.exists():
            logger.error(f"CSV file not found: {csv_path}")
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        if not csv_path.is_file():
            raise ValueError(f"Path is not a file: {csv_path}")

        if args.chunk_size <= 0:
            raise ValueError(f"Chunk size must be positive, got {args.chunk_size}")

        if args.source_width <= 0 or args.target_width <= 0:
            raise ValueError(
                f"Image widths must be positive, got source={args.source_width}, "
                f"target={args.target_width}"
            )

        if args.progress_interval <= 0:
            raise ValueError(f"Progress interval must be positive, got {args.progress_interval}")

        # Run ingestion with progress tracking
        logger.info("=" * 70)
        logger.info("Starting CSV ingestion pipeline...")
        logger.info("=" * 70)

        result = await ingest_with_progress(
            csv_path=csv_path,
            chunk_size=args.chunk_size,
            source_width=args.source_width,
            target_width=args.target_width,
            store_colored=args.store_colored,
            progress_interval=args.progress_interval,
        )

        # Display results banner
        print(f"\n{'='*70}")
        print("INGESTION RESULTS")
        print(f"{'='*70}")
        print(f"Rows Processed:    {result['rows_processed']:,}")
        print(f"Frames Stored:     {result['frames_stored']:,}")
        print(f"DB Count:          {result['db_count']:,}")
        print(f"Validation:        {'✓ PASSED' if result['validation_passed'] else '✗ FAILED'}")
        print("\nPerformance Metrics:")
        print(f"  Total Duration:  {result['duration_seconds']:.2f} seconds")
        print(f"  Throughput:      {result['throughput_fps']:.1f} frames/sec")
        print(f"  Throughput:      {result['throughput_mbps']:.2f} MB/sec")
        print(f"  Est. DB Size:    {result['db_size_mb']:.2f} MB")

        if result["min_depth"] is not None and result["max_depth"] is not None:
            print(
                f"\nDepth Range:       "
                f"{result['min_depth']:.4f} → "
                f"{result['max_depth']:.4f}"
            )

        print("\nTiming Breakdown:")
        print(f"  Explore CSV:     {result['timings']['explore_seconds']:.3f}s")
        print(f"  Process Chunks:  {result['timings']['process_seconds']:.3f}s")
        print(f"  Validate DB:     {result['timings']['validate_seconds']:.3f}s")
        print(f"{'='*70}\n")

        # Final validation checks
        if not result["validation_passed"]:
            logger.error(
                f"Validation FAILED: Processed {result['frames_stored']:,} frames "
                f"but DB contains {result['db_count']:,} frames"
            )
            print(
                "❌ VALIDATION FAILED: Frame count mismatch " "(see logs for details)",
                file=sys.stderr,
            )
            return 2  # Exit code 2 for validation errors

        if result["rows_processed"] != result["frames_stored"]:
            logger.warning(
                f"Row/frame mismatch: {result['rows_processed']:,} rows processed "
                f"but only {result['frames_stored']:,} frames stored. "
                f"Some rows may have been skipped due to invalid data."
            )
            print(
                "⚠️  WARNING: Some rows failed processing " "(check logs for details)",
                file=sys.stderr,
            )
            # This is a warning but not a hard failure
            # Could return 2 here if you want strict validation

        # Success!
        logger.info("=" * 70)
        logger.info("✓ Ingestion completed successfully (idempotent upsert)")
        logger.info("=" * 70)
        print("✓ Ingestion completed successfully")
        print("  Pipeline is idempotent - safe to re-run without duplicates\n")
        return 0

    except FileNotFoundError as e:
        logger.error(f"File error: {e}")
        print(f"\n❌ ERROR: {e}", file=sys.stderr)
        print("   Check that the CSV file path is correct.\n", file=sys.stderr)
        return 1  # Exit code 1 for file errors

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        print(f"\n❌ ERROR: Invalid configuration - {e}", file=sys.stderr)
        print("   Check command-line arguments.\n", file=sys.stderr)
        return 1  # Exit code 1 for config errors

    except Exception as e:
        logger.exception("Unexpected error during ingestion")
        print(f"\n❌ ERROR: Unexpected error - {e}", file=sys.stderr)
        print("   See logs for full traceback.\n", file=sys.stderr)

        # Print traceback for debugging
        import traceback

        traceback.print_exc()

        return 3  # Exit code 3 for unexpected/database errors


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
