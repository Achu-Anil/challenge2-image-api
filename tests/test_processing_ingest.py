"""
Tests for processing.ingest module (app/processing/ingest.py).

These tests cover:
- CSV exploration and validation
- Chunked CSV reading
- Frame processing pipeline
- Database upsert operations
- Complete ingestion workflow
"""

from unittest.mock import patch

import pandas as pd
import pytest

from app.processing.ingest import (
    explore_csv,
    ingest_csv,
    process_chunk_to_frames,
    read_csv_chunks,
    upsert_frames,
)


class TestExploreCSV:
    """Test CSV exploration functionality."""

    def test_explore_csv_basic(self, tmp_path):
        """Test basic CSV exploration."""
        # Create test CSV
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0, 300.0, 400.0, 500.0],
                **{f"col{i}": [i % 256] * 5 for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        # Explore CSV
        info = explore_csv(csv_file)

        # Verify results
        assert info["num_rows"] == 5
        assert info["num_cols"] == 201  # 1 depth + 200 pixels
        assert info["first_column"] == "depth"
        assert info["num_pixel_columns"] == 200
        assert len(info["sample_depths"]) == 5
        assert info["file_size_mb"] > 0

    def test_explore_csv_file_not_found(self, tmp_path):
        """Test CSV exploration with non-existent file."""
        csv_file = tmp_path / "nonexistent.csv"

        with pytest.raises(FileNotFoundError):
            explore_csv(csv_file)

    def test_explore_csv_string_path(self, tmp_path):
        """Test CSV exploration with string path."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0],
                **{f"col{i}": [i % 256] * 2 for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        # Pass as string
        info = explore_csv(str(csv_file))

        assert info["num_rows"] == 2
        assert info["num_cols"] == 201

    def test_explore_csv_large_file_estimate(self, tmp_path):
        """Test memory estimate for large CSV."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [float(i) for i in range(100)],
                **{f"col{i}": [i % 256] * 100 for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        info = explore_csv(csv_file)

        assert info["memory_estimate_mb"] > 0
        assert info["num_rows"] == 100


class TestReadCSVChunks:
    """Test chunked CSV reading."""

    def test_read_csv_chunks_basic(self, tmp_path):
        """Test basic chunked reading."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [float(i) for i in range(10)],
                **{f"col{i}": [i % 256] * 10 for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        # Read in chunks of 3
        chunks = list(read_csv_chunks(csv_file, chunk_size=3))

        # Should have 4 chunks (3+3+3+1)
        assert len(chunks) == 4
        assert len(chunks[0]) == 3
        assert len(chunks[1]) == 3
        assert len(chunks[2]) == 3
        assert len(chunks[3]) == 1

    def test_read_csv_chunks_single_chunk(self, tmp_path):
        """Test reading with chunk size larger than file."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0],
                **{f"col{i}": [i % 256] * 2 for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        chunks = list(read_csv_chunks(csv_file, chunk_size=100))

        assert len(chunks) == 1
        assert len(chunks[0]) == 2

    def test_read_csv_chunks_string_path(self, tmp_path):
        """Test chunked reading with string path."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0, 300.0],
                **{f"col{i}": [i % 256] * 3 for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        chunks = list(read_csv_chunks(str(csv_file), chunk_size=2))

        assert len(chunks) == 2


class TestProcessChunkToFrames:
    """Test chunk processing to frames."""

    @pytest.mark.asyncio
    async def test_process_chunk_basic(self):
        """Test basic chunk processing."""
        # Create test chunk
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0],
                **{f"col{i}": [i % 256, (i + 50) % 256] for i in range(1, 201)},
            }
        )

        frames = await process_chunk_to_frames(df)

        assert len(frames) == 2
        assert frames[0]["depth"] == 100.0
        assert frames[1]["depth"] == 200.0
        assert frames[0]["width"] == 150
        assert frames[0]["height"] == 1
        assert isinstance(frames[0]["image_png"], bytes)

    @pytest.mark.asyncio
    async def test_process_chunk_wrong_column_count(self):
        """Test processing chunk with wrong number of columns."""
        # Create chunk with wrong number of pixel columns
        df = pd.DataFrame(
            {
                "depth": [100.0],
                **{f"col{i}": [i % 256] for i in range(1, 101)},  # Only 100 columns
            }
        )

        with pytest.raises(ValueError, match="Expected 200 pixel columns"):
            await process_chunk_to_frames(df, source_width=200)

    @pytest.mark.asyncio
    async def test_process_chunk_custom_widths(self):
        """Test processing with custom source and target widths."""
        df = pd.DataFrame(
            {
                "depth": [100.0],
                **{f"col{i}": [i % 256] for i in range(1, 101)},  # 100 columns
            }
        )

        frames = await process_chunk_to_frames(df, source_width=100, target_width=75)

        assert len(frames) == 1
        assert frames[0]["width"] == 75

    @pytest.mark.asyncio
    async def test_process_chunk_handles_row_errors(self, caplog):
        """Test that processing continues after row errors."""
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0, 300.0],
                **{f"col{i}": [i % 256, (i + 50) % 256, (i + 100) % 256] for i in range(1, 201)},
            }
        )

        # Mock process_row_to_png to fail on second row
        with patch("app.processing.ingest.process_row_to_png") as mock_process:
            mock_process.side_effect = [
                (b"PNG1", 150, 1),
                ValueError("Processing error"),
                (b"PNG3", 150, 1),
            ]

            frames = await process_chunk_to_frames(df)

            # Should get 2 frames (1st and 3rd)
            assert len(frames) == 2
            assert frames[0]["depth"] == 100.0
            assert frames[1]["depth"] == 300.0

    @pytest.mark.asyncio
    async def test_process_chunk_empty(self):
        """Test processing empty chunk."""
        df = pd.DataFrame(
            {
                "depth": [],
                **{f"col{i}": [] for i in range(1, 201)},
            }
        )

        frames = await process_chunk_to_frames(df)

        assert len(frames) == 0


class TestUpsertFrames:
    """Test database upsert operations."""

    @pytest.mark.asyncio
    async def test_upsert_frames_basic(self, db_session):
        """Test basic frame upsert."""
        frames = [
            {
                "depth": 100.0,
                "image_png": b"PNG_DATA_1",
                "width": 150,
                "height": 1,
            },
            {
                "depth": 200.0,
                "image_png": b"PNG_DATA_2",
                "width": 150,
                "height": 1,
            },
        ]

        count = await upsert_frames(db_session, frames)

        assert count == 2

        # Verify frames were inserted
        from sqlalchemy import select

        from app.db import Frame

        result = await db_session.execute(select(Frame))
        stored_frames = result.scalars().all()

        assert len(stored_frames) >= 2

    @pytest.mark.asyncio
    async def test_upsert_frames_empty_list(self, db_session):
        """Test upserting empty frame list."""
        count = await upsert_frames(db_session, [])

        assert count == 0

    @pytest.mark.asyncio
    async def test_upsert_frames_duplicate_depth(self, db_session):
        """Test upserting frames with duplicate depths (should update)."""
        # Insert initial frame
        frames1 = [
            {
                "depth": 100.0,
                "image_png": b"PNG_DATA_OLD",
                "width": 150,
                "height": 1,
            },
        ]
        await upsert_frames(db_session, frames1)

        # Upsert with same depth but different data
        frames2 = [
            {
                "depth": 100.0,
                "image_png": b"PNG_DATA_NEW",
                "width": 150,
                "height": 1,
            },
        ]
        await upsert_frames(db_session, frames2)

        # Verify update occurred
        from sqlalchemy import select

        from app.db import Frame

        result = await db_session.execute(select(Frame).where(Frame.depth == 100.0))
        frame = result.scalar_one()

        assert frame.image_png == b"PNG_DATA_NEW"


class TestIngestCSV:
    """Test complete CSV ingestion pipeline."""

    @pytest.mark.asyncio
    async def test_ingest_csv_complete_workflow(self, tmp_path):
        """Test complete ingestion workflow."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0, 300.0],
                **{f"col{i}": [i % 256, (i + 50) % 256, (i + 100) % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        result = await ingest_csv(csv_path=csv_file, chunk_size=2)

        assert result["rows_processed"] == 3
        assert result["frames_upserted"] == 3
        assert result["chunk_size"] == 2
        assert result["source_width"] == 200
        assert result["target_width"] == 150
        assert result["duration_seconds"] > 0
        assert result["rows_per_second"] > 0

    @pytest.mark.asyncio
    async def test_ingest_csv_wrong_column_count(self, tmp_path):
        """Test ingestion with wrong number of columns."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0],
                **{f"col{i}": [i % 256] for i in range(1, 101)},  # Only 100 columns
            }
        )
        df.to_csv(csv_file, index=False)

        with pytest.raises(ValueError, match="Expected 201 columns"):
            await ingest_csv(csv_path=csv_file)

    @pytest.mark.asyncio
    async def test_ingest_csv_custom_settings(self, tmp_path):
        """Test ingestion with custom settings."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0],
                **{f"col{i}": [i % 256, (i + 50) % 256] for i in range(1, 101)},
            }
        )
        df.to_csv(csv_file, index=False)

        result = await ingest_csv(
            csv_path=csv_file,
            chunk_size=1,
            source_width=100,
            target_width=75,
        )

        assert result["rows_processed"] == 2
        assert result["chunk_size"] == 1
        assert result["source_width"] == 100
        assert result["target_width"] == 75

    @pytest.mark.asyncio
    async def test_ingest_csv_with_settings_defaults(self, tmp_path):
        """Test ingestion using settings defaults."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0],
                **{f"col{i}": [i % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        # Mock settings
        with patch("app.processing.ingest.settings") as mock_settings:
            mock_settings.csv_file_path = str(csv_file)
            mock_settings.chunk_size = 100

            result = await ingest_csv()

            assert result["rows_processed"] == 1

    @pytest.mark.asyncio
    async def test_ingest_csv_large_file(self, tmp_path):
        """Test ingestion with larger file to verify chunking."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [float(i) for i in range(50)],
                **{f"col{i}": [i % 256] * 50 for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        result = await ingest_csv(csv_path=csv_file, chunk_size=10)

        assert result["rows_processed"] == 50
        assert result["chunks_processed"] == 5  # 50 rows / 10 per chunk

    @pytest.mark.asyncio
    async def test_ingest_csv_performance_metrics(self, tmp_path):
        """Test that performance metrics are calculated."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0],
                **{f"col{i}": [i % 256, (i + 50) % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        result = await ingest_csv(csv_path=csv_file)

        # Verify all metrics are present
        assert "duration_seconds" in result
        assert "rows_per_second" in result
        assert result["duration_seconds"] > 0
        assert result["rows_per_second"] > 0

    @pytest.mark.asyncio
    async def test_ingest_csv_progress_logging(self, tmp_path, caplog):
        """Test that progress is logged during ingestion."""
        csv_file = tmp_path / "test.csv"
        # Create enough rows to trigger progress logging (every 10 chunks)
        df = pd.DataFrame(
            {
                "depth": [float(i) for i in range(100)],
                **{f"col{i}": [i % 256] * 100 for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        with caplog.at_level("INFO"):
            await ingest_csv(csv_path=csv_file, chunk_size=10)

        # Verify logging
        assert "Starting CSV ingestion" in caplog.text
        assert "CSV ingestion complete" in caplog.text
