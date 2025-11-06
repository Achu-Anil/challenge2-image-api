"""
CSV Ingestion CLI Tool

This script reads a CSV file containing depth-keyed grayscale image data,
processes each row (resize, colorize, encode to PNG), and stores the results
in the database.

CSV Format:
    depth,col1,col2,...,col200
    100.5,45,67,89,...,234

Where:
    - First column: depth (float) - unique identifier
    - Next 200 columns: pixel intensity values (0-255)

Processing Pipeline:
    1. Read CSV in chunks (default: 500 rows) using pandas
    2. For each row:
       - Extract depth and 200 pixel values
       - Resize from 200px → 150px (bilinear interpolation)
       - Apply colormap LUT (grayscale → RGB)
       - Encode as PNG
    3. Upsert to database (idempotent - overwrites on duplicate depth)
    4. Log progress and metrics

Usage:
    # From Docker
    docker compose exec api python -m app.cli.ingest /app/data/yourfile.csv

    # From local environment
    poetry run python -m app.cli.ingest data/yourfile.csv --chunk-size 1000

    # With custom chunk size
    python -m app.cli.ingest data/large_file.csv --chunk-size 1000
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

import pandas as pd

from app.core import get_logger, settings, setup_logging
from app.db import get_db_context, upsert_frame
from app.processing import process_row_to_png

# Initialize logging
setup_logging(settings.log_level)
logger = get_logger(__name__)


async def ingest_csv(
    csv_path: Path,
    chunk_size: int = 500,
) -> dict:
    """
    Ingest CSV file into database.

    Reads the CSV in chunks, processes each row (resize, colorize, encode),
    and upserts to the database. Progress is logged every chunk.

    Args:
        csv_path: Path to CSV file
        chunk_size: Number of rows to process per batch (default: 500)

    Returns:
        dict: Ingestion statistics

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If CSV format is invalid
    """
    # ========================================
    # Validation
    # ========================================
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    logger.info(
        "Starting CSV ingestion",
        extra={
            "csv_path": str(csv_path),
            "chunk_size": chunk_size,
            "file_size_mb": csv_path.stat().st_size / (1024 * 1024),
        },
    )

    # No need to pre-compute colormap - process_row_to_png handles everything!

    # ========================================
    # CSV Processing
    # ========================================
    total_rows = 0
    successful_rows = 0
    failed_rows = 0
    start_time = time.time()

    try:
        # Read CSV in chunks to avoid loading entire file into memory
        # This is crucial for large datasets (millions of rows)
        csv_reader = pd.read_csv(
            csv_path,
            chunksize=chunk_size,
            na_filter=False,  # Don't convert empty strings to NaN - prevents IntCastingNaNError
            dtype={
                "depth": float,  # First column is depth
                **{f"col{i}": "uint8" for i in range(1, 201)},  # Next 200 columns are pixel values
            },
        )

        chunk_num = 0

        # Process each chunk
        for chunk_df in csv_reader:
            chunk_num += 1
            chunk_start = time.time()

            # Get database session for this chunk
            async with get_db_context() as session:
                # Process each row in the chunk
                for idx, row in chunk_df.iterrows():
                    try:
                        # Extract depth value (primary key)
                        depth = float(row["depth"])

                        # Extract pixel values (200 columns)
                        # Note: CSV columns are named col1-col200, not 0-199
                        pixel_values = row[[f"col{i}" for i in range(1, 201)]].values

                        # ========================================
                        # Image Processing Pipeline
                        # ========================================
                        # One-stop shop: resize (200→150) + colormap + PNG encoding
                        # This helper function does all the heavy lifting! 🚀
                        png_bytes, width, height = process_row_to_png(
                            row_data=pixel_values, source_width=200, target_width=150
                        )

                        # ========================================
                        # Database Upsert
                        # ========================================
                        # Upsert = INSERT or UPDATE (idempotent ingestion)
                        # If depth already exists, we overwrite with new data
                        await upsert_frame(
                            session=session,
                            depth=depth,
                            width=width,
                            height=height,
                            png_bytes=png_bytes,
                        )

                        successful_rows += 1

                    except Exception as e:
                        failed_rows += 1
                        logger.error(
                            f"Failed to process row {idx}",
                            extra={
                                "error": str(e),
                                "depth": row.get("depth", "unknown"),
                            },
                        )

                # Commit the chunk
                await session.commit()

            # ========================================
            # Progress Logging
            # ========================================
            total_rows += len(chunk_df)
            chunk_duration = time.time() - chunk_start
            rows_per_sec = len(chunk_df) / chunk_duration if chunk_duration > 0 else 0

            logger.info(
                f"Processed chunk {chunk_num}",
                extra={
                    "chunk_size": len(chunk_df),
                    "total_rows": total_rows,
                    "successful": successful_rows,
                    "failed": failed_rows,
                    "chunk_duration_sec": round(chunk_duration, 2),
                    "rows_per_sec": round(rows_per_sec, 1),
                },
            )

    except Exception as e:
        logger.error(
            "CSV ingestion failed",
            extra={
                "error": str(e),
                "total_rows_processed": total_rows,
            },
        )
        raise

    # ========================================
    # Final Statistics
    # ========================================
    total_duration = time.time() - start_time
    avg_rows_per_sec = total_rows / total_duration if total_duration > 0 else 0

    stats = {
        "total_rows": total_rows,
        "successful": successful_rows,
        "failed": failed_rows,
        "duration_sec": round(total_duration, 2),
        "avg_rows_per_sec": round(avg_rows_per_sec, 1),
    }

    logger.info(
        "CSV ingestion complete",
        extra=stats,
    )

    return stats


def main() -> None:
    """
    CLI entry point for CSV ingestion.

    Parses command-line arguments and runs the ingestion process.
    """
    # ========================================
    # Argument Parsing
    # ========================================
    parser = argparse.ArgumentParser(
        description="Ingest CSV file of depth-keyed grayscale images into database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Ingest with default chunk size (500)
    python -m app.cli.ingest data/frames.csv

    # Ingest with custom chunk size
    python -m app.cli.ingest data/large_file.csv --chunk-size 1000

    # From Docker container
    docker compose exec api python -m app.cli.ingest /app/data/frames.csv
        """,
    )

    parser.add_argument(
        "csv_path",
        type=Path,
        help="Path to CSV file containing depth and pixel data",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Number of rows to process per batch (default: 500)",
    )

    args = parser.parse_args()

    # ========================================
    # Run Ingestion
    # ========================================
    try:
        # Run async function in event loop
        stats = asyncio.run(
            ingest_csv(
                csv_path=args.csv_path,
                chunk_size=args.chunk_size,
            )
        )

        # Print summary to stdout (for human readability)
        print("\n" + "=" * 60)
        print("✅ Ingestion Complete!")
        print("=" * 60)
        print(f"Total rows:       {stats['total_rows']:,}")
        print(f"Successful:       {stats['successful']:,}")
        print(f"Failed:           {stats['failed']:,}")
        print(f"Duration:         {stats['duration_sec']:.2f} seconds")
        print(f"Throughput:       {stats['avg_rows_per_sec']:.1f} rows/sec")
        print("=" * 60 + "\n")

        # Exit with success
        sys.exit(0)

    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        print(f"\n❌ Error: {e}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
