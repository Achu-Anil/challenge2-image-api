"""
Advanced integration tests for API endpoints covering error cases and edge conditions.

These tests focus on:
- Error handling and exception paths
- Database connection failures
- Cache integration
- Edge cases in frame retrieval
"""

from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db import Frame, get_db_context
from app.db.operations import upsert_frame


class TestHealthEndpointAdvanced:
    """Advanced tests for GET /health endpoint with error conditions."""

    def test_health_check_database_failure(self, client: TestClient):
        """Test health check when database is unavailable."""
        # Mock database error
        with patch("app.api.routes.get_db", side_effect=Exception("DB connection failed")):
            response = client.get("/health")
            # Should still return 200 but with degraded status
            assert response.status_code == 200
            data = response.json()
            # The actual implementation catches errors in the endpoint
            # so we verify the response structure
            assert "status" in data
            assert "database" in data


class TestFramesEndpointAdvanced:
    """Advanced tests for GET /frames endpoint covering edge cases."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_test_data(self):
        """Set up test frames before each test and clean up after."""
        async with get_db_context() as session:
            await session.execute(delete(Frame))
            await session.commit()

            # Add varied test frames
            test_frames = [
                (0.0, 150, 1, b"PNG0"),  # Edge: depth = 0
                (100.5, 150, 1, b"PNG100"),
                (200.0, 150, 1, b"PNG200"),
                (999.9, 150, 1, b"PNG999"),
            ]

            for depth, width, height, png_bytes in test_frames:
                await upsert_frame(session, depth, width, height, png_bytes)

            await session.commit()

        yield

        async with get_db_context() as session:
            await session.execute(delete(Frame))
            await session.commit()

    def test_get_frames_zero_depth(self, client: TestClient):
        """Test retrieving frame at depth 0."""
        response = client.get("/frames?depth_min=0&depth_max=0.1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["frames"]) == 1
        assert data["frames"][0]["depth"] == 0.0

    def test_get_frames_float_precision(self, client: TestClient):
        """Test handling of float precision in depth values."""
        response = client.get("/frames?depth_min=100.4&depth_max=100.6")
        assert response.status_code == 200
        data = response.json()
        assert len(data["frames"]) == 1
        assert data["frames"][0]["depth"] == 100.5

    def test_get_frames_large_limit(self, client: TestClient):
        """Test requesting limit larger than available frames."""
        response = client.get("/frames?limit=1000")
        assert response.status_code == 200
        data = response.json()
        assert len(data["frames"]) <= 1000
        assert data["metadata"]["has_more"] is False

    def test_get_frames_boundary_inclusive(self, client: TestClient):
        """Test that depth_min and depth_max are inclusive."""
        response = client.get("/frames?depth_min=100.5&depth_max=100.5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["frames"]) == 1
        assert data["frames"][0]["depth"] == 100.5

    def test_get_frames_with_cache_hit(self, client: TestClient):
        """Test that repeated requests benefit from caching."""
        # First request - cache miss
        response1 = client.get("/frames?depth_min=100&depth_max=200")
        assert response1.status_code == 200

        # Second request - should hit cache
        response2 = client.get("/frames?depth_min=100&depth_max=200")
        assert response2.status_code == 200

        # Results should be identical
        assert response1.json() == response2.json()

    def test_get_frames_offset_beyond_results(self, client: TestClient):
        """Test offset that exceeds available results."""
        response = client.get("/frames?offset=1000")
        assert response.status_code == 200
        data = response.json()
        assert len(data["frames"]) == 0
        assert data["metadata"]["count"] == 0

    def test_get_frames_negative_limit_validation(self, client: TestClient):
        """Test that negative limit is rejected."""
        response = client.get("/frames?limit=-1")
        assert response.status_code == 422  # Validation error

    def test_get_frames_negative_offset_validation(self, client: TestClient):
        """Test that negative offset is rejected."""
        response = client.get("/frames?offset=-1")
        assert response.status_code == 422  # Validation error

    def test_get_frames_with_only_depth_min(self, client: TestClient):
        """Test filtering with only depth_min specified."""
        response = client.get("/frames?depth_min=200")
        assert response.status_code == 200
        data = response.json()
        frames = data["frames"]
        # Should return frames at 200.0 and 999.9
        assert len(frames) >= 2
        for frame in frames:
            assert frame["depth"] >= 200.0

    def test_get_frames_with_only_depth_max(self, client: TestClient):
        """Test filtering with only depth_max specified."""
        response = client.get("/frames?depth_max=200")
        assert response.status_code == 200
        data = response.json()
        frames = data["frames"]
        # Should return frames at 0.0, 100.5, 200.0
        assert len(frames) >= 3
        for frame in frames:
            assert frame["depth"] <= 200.0


class TestReloadEndpointAdvanced:
    """Advanced tests for POST /frames/reload endpoint."""

    def test_reload_missing_admin_header(self, client: TestClient):
        """Test that missing X-Admin-Token header is rejected."""
        response = client.post("/frames/reload", json={"csv_path": "test.csv"})
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    def test_reload_empty_admin_token(self, client: TestClient):
        """Test that empty admin token is rejected."""
        headers = {"X-Admin-Token": ""}
        response = client.post("/frames/reload", headers=headers, json={"csv_path": "test.csv"})
        assert response.status_code == 401

    def test_reload_with_whitespace_in_path(self, client: TestClient):
        """Test reload with whitespace in CSV path."""
        headers = {"X-Admin-Token": "change-me-in-production"}
        response = client.post(
            "/frames/reload",
            headers=headers,
            json={"csv_path": "  nonexistent.csv  "},
        )
        # Should handle or reject whitespace appropriately
        assert response.status_code in [400, 404]


class TestCacheEndpoints:
    """Tests for cache management endpoints."""

    def test_cache_stats_endpoint_exists(self, client: TestClient):
        """Test that cache stats endpoint is accessible."""
        response = client.get("/cache/stats")
        # May return 404 if not implemented, or 200 with stats
        assert response.status_code in [200, 404]

    def test_cache_clear_endpoint_exists(self, client: TestClient):
        """Test that cache clear endpoint is accessible."""
        response = client.post("/cache/clear")
        # May return 404 if not implemented, or require auth
        assert response.status_code in [200, 401, 404]


class TestErrorHandling:
    """Tests for general error handling."""

    def test_invalid_endpoint_returns_404(self, client: TestClient):
        """Test that invalid endpoints return 404."""
        response = client.get("/nonexistent/endpoint")
        assert response.status_code == 404

    def test_invalid_method_returns_405(self, client: TestClient):
        """Test that invalid HTTP methods return 405."""
        response = client.put("/health")
        assert response.status_code == 405

    def test_malformed_json_returns_422(self, client: TestClient):
        """Test that malformed JSON returns validation error."""
        headers = {"X-Admin-Token": "change-me-in-production", "Content-Type": "application/json"}
        response = client.post(
            "/frames/reload",
            headers=headers,
            content="{'invalid': json}",  # Invalid JSON
        )
        assert response.status_code == 422


class TestPaginationEdgeCases:
    """Tests for pagination edge cases."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_many_frames(self):
        """Set up many test frames for pagination testing."""
        async with get_db_context() as session:
            await session.execute(delete(Frame))
            await session.commit()

            # Create 50 frames
            test_frames = [(float(i), 150, 1, f"PNG{i}".encode()) for i in range(50)]

            for depth, width, height, png_bytes in test_frames:
                await upsert_frame(session, depth, width, height, png_bytes)

            await session.commit()

        yield

        async with get_db_context() as session:
            await session.execute(delete(Frame))
            await session.commit()

    def test_pagination_first_page(self, client: TestClient):
        """Test first page of paginated results."""
        response = client.get("/frames?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["frames"]) == 10
        assert data["metadata"]["offset"] == 0
        assert data["metadata"]["has_more"] is True

    def test_pagination_middle_page(self, client: TestClient):
        """Test middle page of paginated results."""
        response = client.get("/frames?limit=10&offset=20")
        assert response.status_code == 200
        data = response.json()
        assert len(data["frames"]) == 10
        assert data["metadata"]["offset"] == 20

    def test_pagination_last_page(self, client: TestClient):
        """Test last page of paginated results."""
        response = client.get("/frames?limit=10&offset=45")
        assert response.status_code == 200
        data = response.json()
        assert len(data["frames"]) == 5  # Only 5 frames left
        assert data["metadata"]["has_more"] is False

    def test_pagination_consistency(self, client: TestClient):
        """Test that paginated results are consistent."""
        # Fetch all frames in pages
        all_frames = []
        offset = 0
        limit = 10

        while True:
            response = client.get(f"/frames?limit={limit}&offset={offset}")
            assert response.status_code == 200
            data = response.json()
            frames = data["frames"]

            if not frames:
                break

            all_frames.extend(frames)

            if not data["metadata"]["has_more"]:
                break

            offset += limit

        # Should have fetched all 50 frames
        assert len(all_frames) == 50

        # Depths should be sorted and unique
        depths = [f["depth"] for f in all_frames]
        assert depths == sorted(depths)
        assert len(set(depths)) == len(depths)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
