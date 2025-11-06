"""
Tests for CLI ingestion module (app/cli/ingest.py).

These tests cover the command-line ingestion tool including:
- CSV file validation and error handling
- Async ingestion pipeline
- Progress tracking and statistics
- CLI argument parsing
- Error recovery and reporting
"""

import sys
from unittest.mock import patch

import pandas as pd
import pytest

from app.cli.ingest import ingest_csv, main


class TestIngestCSV:
    """Test the async CSV ingestion function."""

    @pytest.mark.asyncio
    async def test_ingest_csv_success(self, tmp_path):
        """Test successful CSV ingestion with valid data."""
        # Create a test CSV file
        csv_file = tmp_path / "test_data.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0, 300.0],
                **{f"col{i}": [i % 256, (i + 50) % 256, (i + 100) % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        # Run ingestion
        stats = await ingest_csv(csv_path=csv_file, chunk_size=2)

        # Verify statistics
        assert stats["total_rows"] == 3
        assert stats["successful"] == 3
        assert stats["failed"] == 0
        assert stats["duration_sec"] > 0
        assert stats["avg_rows_per_sec"] > 0

    @pytest.mark.asyncio
    async def test_ingest_csv_file_not_found(self, tmp_path):
        """Test ingestion with non-existent CSV file."""
        csv_file = tmp_path / "nonexistent.csv"

        with pytest.raises(FileNotFoundError, match="CSV file not found"):
            await ingest_csv(csv_path=csv_file)

    @pytest.mark.asyncio
    async def test_ingest_csv_chunked_processing(self, tmp_path):
        """Test that CSV is processed in chunks."""
        # Create a larger test CSV
        csv_file = tmp_path / "test_data.csv"
        df = pd.DataFrame(
            {
                "depth": [float(i) for i in range(10)],
                **{f"col{i}": [i % 256] * 10 for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        # Use small chunk size to test chunking
        stats = await ingest_csv(csv_path=csv_file, chunk_size=3)

        assert stats["total_rows"] == 10
        assert stats["successful"] == 10

    @pytest.mark.asyncio
    async def test_ingest_csv_handles_row_errors(self, tmp_path):
        """Test that ingestion continues after row processing errors."""
        # Create test CSV with some invalid data
        csv_file = tmp_path / "test_data.csv"

        # Create valid data
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0, 300.0],
                **{f"col{i}": [i % 256, (i + 50) % 256, (i + 100) % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        # Mock process_row_to_png to fail on second row
        with patch("app.cli.ingest.process_row_to_png") as mock_process:
            mock_process.side_effect = [
                (b"PNG_DATA_1", 150, 1),
                ValueError("Processing error"),
                (b"PNG_DATA_3", 150, 1),
            ]

            stats = await ingest_csv(csv_path=csv_file, chunk_size=5)

            # Should continue processing despite error
            assert stats["total_rows"] == 3
            assert stats["successful"] == 2
            assert stats["failed"] == 1

    @pytest.mark.asyncio
    async def test_ingest_csv_empty_file(self, tmp_path):
        """Test ingestion with empty CSV file."""
        csv_file = tmp_path / "empty.csv"
        df = pd.DataFrame(
            {
                "depth": [],
                **{f"col{i}": [] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        stats = await ingest_csv(csv_path=csv_file)

        assert stats["total_rows"] == 0
        assert stats["successful"] == 0
        assert stats["failed"] == 0

    @pytest.mark.asyncio
    async def test_ingest_csv_progress_logging(self, tmp_path, caplog):
        """Test that progress is logged during ingestion."""
        csv_file = tmp_path / "test_data.csv"
        df = pd.DataFrame(
            {
                "depth": [float(i) for i in range(5)],
                **{f"col{i}": [i % 256] * 5 for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        with caplog.at_level("INFO"):
            await ingest_csv(csv_path=csv_file, chunk_size=2)

        # Check that progress was logged
        assert "Starting CSV ingestion" in caplog.text
        assert "Processed chunk" in caplog.text
        assert "CSV ingestion complete" in caplog.text


class TestCLIMain:
    """Test the CLI main function and argument parsing."""

    def test_main_success(self, tmp_path, monkeypatch):
        """Test successful CLI execution."""
        # Create test CSV
        csv_file = tmp_path / "test_data.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0],
                **{f"col{i}": [i % 256, (i + 50) % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        # Mock sys.argv
        test_args = ["ingest.py", str(csv_file)]
        monkeypatch.setattr(sys, "argv", test_args)

        # Mock sys.exit to capture exit code
        exit_code = None

        def mock_exit(code):
            nonlocal exit_code
            exit_code = code
            raise SystemExit(code)

        monkeypatch.setattr(sys, "exit", mock_exit)

        # Run main
        try:
            main()
        except SystemExit:
            pass

        # Should exit with 0 (success)
        assert exit_code == 0

    def test_main_with_chunk_size(self, tmp_path, monkeypatch):
        """Test CLI with custom chunk size argument."""
        csv_file = tmp_path / "test_data.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0],
                **{f"col{i}": [i % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        test_args = ["ingest.py", str(csv_file), "--chunk-size", "100"]
        monkeypatch.setattr(sys, "argv", test_args)

        exit_code = None

        def mock_exit(code):
            nonlocal exit_code
            exit_code = code
            raise SystemExit(code)

        monkeypatch.setattr(sys, "exit", mock_exit)

        try:
            main()
        except SystemExit:
            pass

        assert exit_code == 0

    def test_main_file_not_found(self, tmp_path, monkeypatch, capsys):
        """Test CLI with non-existent file."""
        csv_file = tmp_path / "nonexistent.csv"

        test_args = ["ingest.py", str(csv_file)]
        monkeypatch.setattr(sys, "argv", test_args)

        exit_code = None

        def mock_exit(code):
            nonlocal exit_code
            exit_code = code
            raise SystemExit(code)

        monkeypatch.setattr(sys, "exit", mock_exit)

        try:
            main()
        except SystemExit:
            pass

        # Should exit with 1 (error)
        assert exit_code == 1

        # Check error message in stderr
        captured = capsys.readouterr()
        assert "Error" in captured.err or "Error" in captured.out

    def test_main_invalid_chunk_size(self, tmp_path, monkeypatch):
        """Test CLI with invalid chunk size."""
        csv_file = tmp_path / "test_data.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0],
                **{f"col{i}": [i % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        test_args = ["ingest.py", str(csv_file), "--chunk-size", "invalid"]
        monkeypatch.setattr(sys, "argv", test_args)

        # Should raise SystemExit due to argparse error
        with pytest.raises(SystemExit):
            main()

    def test_main_prints_summary(self, tmp_path, monkeypatch, capsys):
        """Test that main prints ingestion summary."""
        csv_file = tmp_path / "test_data.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0],
                **{f"col{i}": [i % 256, (i + 50) % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        test_args = ["ingest.py", str(csv_file)]
        monkeypatch.setattr(sys, "argv", test_args)

        exit_code = None

        def mock_exit(code):
            nonlocal exit_code
            exit_code = code
            raise SystemExit(code)

        monkeypatch.setattr(sys, "exit", mock_exit)

        try:
            main()
        except SystemExit:
            pass

        captured = capsys.readouterr()
        output = captured.out + captured.err

        # Check for summary elements
        assert "Ingestion Complete" in output or "Complete" in output
        assert "Total rows" in output or "rows" in output

    @patch("app.cli.ingest.asyncio.run")
    def test_main_handles_ingestion_error(self, mock_run, tmp_path, monkeypatch, capsys):
        """Test that main handles ingestion errors gracefully."""
        csv_file = tmp_path / "test_data.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0],
                **{f"col{i}": [i % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        # Mock asyncio.run to raise an exception
        mock_run.side_effect = RuntimeError("Database connection failed")

        test_args = ["ingest.py", str(csv_file)]
        monkeypatch.setattr(sys, "argv", test_args)

        exit_code = None

        def mock_exit(code):
            nonlocal exit_code
            exit_code = code
            raise SystemExit(code)

        monkeypatch.setattr(sys, "exit", mock_exit)

        try:
            main()
        except SystemExit:
            pass

        # Should exit with error code
        assert exit_code == 1

        # Check error output
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert "Error" in output or "failed" in output


class TestCLIInit:
    """Test CLI package __init__.py exports."""

    def test_ingest_main_exported(self):
        """Test that ingest_main is exported from cli package."""
        from app.cli import ingest_main

        assert callable(ingest_main)
        assert ingest_main.__name__ == "main"
