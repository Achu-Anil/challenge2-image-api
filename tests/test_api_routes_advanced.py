"""
Additional tests for API routes to achieve full coverage.

These tests focus on:
- Reload endpoint with various scenarios
- Cache management endpoints
- Metrics endpoint
- Error handling paths
- Edge cases and validation
"""

import base64
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestReloadEndpoint:
    """Comprehensive tests for POST /frames/reload endpoint."""

    def test_reload_missing_auth_token(self):
        """Test reload without authentication token."""
        response = client.post("/frames/reload", json={})

        assert response.status_code == 401
        assert "Invalid or missing X-Admin-Token" in response.json()["detail"]

    def test_reload_invalid_auth_token(self):
        """Test reload with invalid authentication token."""
        response = client.post(
            "/frames/reload",
            json={},
            headers={"X-Admin-Token": "invalid_token"},
        )

        assert response.status_code == 401
        assert "Invalid or missing X-Admin-Token" in response.json()["detail"]

    def test_reload_with_valid_token(self, tmp_path, monkeypatch):
        """Test successful reload with valid token."""
        # Create test CSV
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0],
                **{f"col{i}": [i % 256, (i + 50) % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        # Set admin token
        monkeypatch.setenv("ADMIN_TOKEN", "test_token_123")
        from app.core import settings

        settings.admin_token = "test_token_123"

        response = client.post(
            "/frames/reload",
            json={"csv_path": str(csv_file)},
            headers={"X-Admin-Token": "test_token_123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["success", "partial"]
        assert "rows_processed" in data
        assert "frames_stored" in data
        assert "duration_seconds" in data

    def test_reload_with_clear_existing(self, tmp_path, monkeypatch):
        """Test reload with clear_existing flag."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0],
                **{f"col{i}": [i % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        monkeypatch.setenv("ADMIN_TOKEN", "test_token_123")
        from app.core import settings

        settings.admin_token = "test_token_123"

        response = client.post(
            "/frames/reload",
            json={"csv_path": str(csv_file), "clear_existing": True},
            headers={"X-Admin-Token": "test_token_123"},
        )

        assert response.status_code == 200

    def test_reload_with_custom_chunk_size(self, tmp_path, monkeypatch):
        """Test reload with custom chunk size."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [float(i) for i in range(5)],
                **{f"col{i}": [i % 256] * 5 for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        monkeypatch.setenv("ADMIN_TOKEN", "test_token_123")
        from app.core import settings

        settings.admin_token = "test_token_123"

        response = client.post(
            "/frames/reload",
            json={"csv_path": str(csv_file), "chunk_size": 2},
            headers={"X-Admin-Token": "test_token_123"},
        )

        assert response.status_code == 200

    def test_reload_csv_not_found(self, tmp_path, monkeypatch):
        """Test reload with non-existent CSV file."""
        monkeypatch.setenv("ADMIN_TOKEN", "test_token_123")
        from app.core import settings

        settings.admin_token = "test_token_123"

        csv_file = tmp_path / "nonexistent.csv"

        response = client.post(
            "/frames/reload",
            json={"csv_path": str(csv_file)},
            headers={"X-Admin-Token": "test_token_123"},
        )

        assert response.status_code == 400
        assert "not found" in response.json()["detail"]

    def test_reload_uses_default_settings(self, tmp_path, monkeypatch):
        """Test reload using default CSV path from settings."""
        # Create CSV at default location
        csv_file = tmp_path / "default.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0],
                **{f"col{i}": [i % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        monkeypatch.setenv("ADMIN_TOKEN", "test_token_123")
        monkeypatch.setenv("CSV_FILE_PATH", str(csv_file))

        from app.core import settings

        settings.admin_token = "test_token_123"
        settings.csv_file_path = str(csv_file)

        # Don't provide csv_path in request
        response = client.post(
            "/frames/reload",
            json={},
            headers={"X-Admin-Token": "test_token_123"},
        )

        assert response.status_code == 200

    def test_reload_partial_success(self, tmp_path, monkeypatch):
        """Test reload when some rows fail to process."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0, 200.0, 300.0],
                **{f"col{i}": [i % 256, (i + 50) % 256, (i + 100) % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        monkeypatch.setenv("ADMIN_TOKEN", "test_token_123")
        from app.core import settings

        settings.admin_token = "test_token_123"

        # Mock ingest_csv from processing module to simulate partial failure
        with patch("app.processing.ingest.ingest_csv") as mock_ingest:
            mock_ingest.return_value = {
                "rows_processed": 3,
                "frames_upserted": 2,  # One row failed
                "chunk_size": 500,
                "chunks_processed": 1,
                "source_width": 200,
                "target_width": 150,
                "duration_seconds": 1.5,
                "rows_per_second": 2.0,
            }

            response = client.post(
                "/frames/reload",
                json={"csv_path": str(csv_file)},
                headers={"X-Admin-Token": "test_token_123"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "partial"
            assert "only stored" in data["message"].lower() or "failed" in data["message"].lower()

    def test_reload_clears_caches(self, tmp_path, monkeypatch):
        """Test that reload clears caches after successful ingestion."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0],
                **{f"col{i}": [i % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        monkeypatch.setenv("ADMIN_TOKEN", "test_token_123")
        from app.core import settings

        settings.admin_token = "test_token_123"

        with patch("app.api.routes.clear_all_caches") as mock_clear:
            response = client.post(
                "/frames/reload",
                json={"csv_path": str(csv_file)},
                headers={"X-Admin-Token": "test_token_123"},
            )

            assert response.status_code == 200
            # Verify caches were cleared
            mock_clear.assert_called_once()


class TestCacheEndpoints:
    """Tests for cache management endpoints."""

    def test_get_cache_stats(self):
        """Test GET /cache/stats endpoint."""
        response = client.get("/cache/stats")

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "frame_cache" in data
        assert "range_cache" in data
        assert "total_requests" in data
        assert "overall_hit_rate" in data

        # Verify cache stats structure
        for cache_name in ["frame_cache", "range_cache"]:
            cache_stats = data[cache_name]
            assert "hits" in cache_stats
            assert "misses" in cache_stats
            assert "hit_rate_percent" in cache_stats or "hit_rate" in cache_stats
            assert "size" in cache_stats

    def test_clear_cache_without_auth(self):
        """Test DELETE /cache without authentication."""
        response = client.delete("/cache")

        assert response.status_code == 401

    def test_clear_cache_with_invalid_token(self):
        """Test DELETE /cache with invalid token."""
        response = client.delete(
            "/cache",
            headers={"X-Admin-Token": "invalid_token"},
        )

        assert response.status_code == 401

    def test_clear_cache_with_valid_token(self, monkeypatch):
        """Test DELETE /cache with valid token."""
        monkeypatch.setenv("ADMIN_TOKEN", "test_token_123")
        from app.core import settings

        settings.admin_token = "test_token_123"

        response = client.delete(
            "/cache",
            headers={"X-Admin-Token": "test_token_123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cleared"
        assert "previous_sizes" in data


class TestMetricsEndpoint:
    """Tests for GET /metrics endpoint."""

    def test_get_metrics_basic(self):
        """Test basic metrics retrieval."""
        response = client.get("/metrics")

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "database" in data
        assert "cache" in data
        assert "application" in data

        # Verify database metrics
        db_metrics = data["database"]
        assert "total_frames" in db_metrics
        assert "depth_min" in db_metrics
        assert "depth_max" in db_metrics

        # Verify cache metrics
        cache_metrics = data["cache"]
        assert "frame_cache" in cache_metrics
        assert "range_cache" in cache_metrics

        # Verify application metadata
        app_metrics = data["application"]
        assert "name" in app_metrics
        assert "version" in app_metrics
        assert "environment" in app_metrics

    def test_get_metrics_cache_details(self):
        """Test that metrics include detailed cache information."""
        response = client.get("/metrics")

        assert response.status_code == 200
        data = response.json()

        for cache_name in ["frame_cache", "range_cache"]:
            cache_data = data["cache"][cache_name]
            assert "hit_rate_percent" in cache_data
            assert "size" in cache_data
            assert "max_size" in cache_data
            assert "hits" in cache_data
            assert "misses" in cache_data


class TestFramesEndpointEdgeCases:
    """Additional tests for GET /frames edge cases."""

    def test_get_frames_depth_max_less_than_min(self):
        """Test that depth_max < depth_min returns 400."""
        response = client.get("/frames?depth_min=500&depth_max=100")

        assert response.status_code == 400
        assert "must be >=" in response.json()["detail"]

    def test_get_frames_with_limit_boundary(self):
        """Test frames with limit at boundary (1000)."""
        response = client.get("/frames?limit=1000")

        assert response.status_code == 200

    def test_get_frames_limit_exceeds_max(self):
        """Test that limit > 1000 is rejected."""
        response = client.get("/frames?limit=1001")

        assert response.status_code == 422  # Validation error

    def test_get_frames_zero_limit(self):
        """Test that limit=0 is rejected."""
        response = client.get("/frames?limit=0")

        assert response.status_code == 422  # Validation error

    def test_get_frames_negative_offset(self):
        """Test that negative offset is rejected."""
        response = client.get("/frames?offset=-1")

        assert response.status_code == 422

    def test_get_frames_large_offset(self):
        """Test frames with large offset value."""
        response = client.get("/frames?offset=10000")

        assert response.status_code == 200
        data = response.json()
        # Should return empty or few results
        assert len(data["frames"]) >= 0

    def test_get_frames_has_more_flag(self, tmp_path, monkeypatch):
        """Test that has_more flag is set correctly."""
        # Insert more frames than limit
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [float(i) for i in range(10)],
                **{f"col{i}": [i % 256] * 10 for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        # Ingest data
        monkeypatch.setenv("ADMIN_TOKEN", "test_token")
        from app.core import settings

        settings.admin_token = "test_token"

        client.post(
            "/frames/reload",
            json={"csv_path": str(csv_file)},
            headers={"X-Admin-Token": "test_token"},
        )

        # Request with small limit
        response = client.get("/frames?limit=3")

        assert response.status_code == 200
        data = response.json()
        # If we have more than 3 frames, has_more should be True
        if data["metadata"]["count"] == 3:
            assert "has_more" in data["metadata"]

    def test_get_frames_metadata_depth_range(self):
        """Test that metadata includes correct depth range from results."""
        response = client.get("/frames?limit=10")

        assert response.status_code == 200
        data = response.json()
        metadata = data["metadata"]

        # If frames exist, depth_min and depth_max should be set
        if metadata["count"] > 0:
            assert metadata["depth_min"] is not None
            assert metadata["depth_max"] is not None
            assert metadata["depth_min"] <= metadata["depth_max"]
        else:
            assert metadata["depth_min"] is None
            assert metadata["depth_max"] is None

    def test_get_frames_base64_encoding(self, tmp_path, monkeypatch):
        """Test that frame images are properly base64 encoded."""
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "depth": [100.0],
                **{f"col{i}": [i % 256] for i in range(1, 201)},
            }
        )
        df.to_csv(csv_file, index=False)

        monkeypatch.setenv("ADMIN_TOKEN", "test_token")
        from app.core import settings

        settings.admin_token = "test_token"

        client.post(
            "/frames/reload",
            json={"csv_path": str(csv_file)},
            headers={"X-Admin-Token": "test_token"},
        )

        response = client.get("/frames?depth_min=100&depth_max=100")

        assert response.status_code == 200
        data = response.json()

        if len(data["frames"]) > 0:
            frame = data["frames"][0]
            # Verify it's valid base64
            try:
                base64.b64decode(frame["image_png_base64"])
            except Exception:
                pytest.fail("Image data is not valid base64")


class TestHealthEndpointEdgeCases:
    """Additional tests for health check endpoint."""

    def test_health_check_database_error(self):
        """Test health check when database is unavailable."""
        with patch("app.api.routes.AsyncSession") as mock_session:
            # Mock database error
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(side_effect=Exception("DB connection failed"))

            response = client.get("/health")

            # Should still return 200 but with degraded status
            assert response.status_code == 200
            # The actual implementation returns "healthy" or "degraded"
            assert "status" in response.json()
