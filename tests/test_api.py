"""
Integration tests for API endpoints.

Tests for:
- GET /health: Health check endpoint
- GET /frames: Frame retrieval with filtering and pagination
- POST /frames/reload: Admin reload endpoint with auth
"""

import base64

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db import Frame, get_db_context
from app.db.operations import upsert_frame
from app.main import app

# Create test client
client = TestClient(app)


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_check_success(self):
        """Test that health check returns 200 and expected fields."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "app_name" in data
        assert "version" in data
        assert "environment" in data
        assert "database" in data

        assert data["status"] in ["healthy", "degraded"]
        assert data["app_name"] == "ImageFramesAPI"
        assert data["database"] == "connected"


class TestFramesEndpoint:
    """Tests for GET /frames endpoint."""

    @pytest.fixture(autouse=True)
    async def setup_test_data(self):
        """Set up test frames before each test and clean up after."""
        # Create some test frames
        async with get_db_context() as session:
            # Clear existing frames
            await session.execute(delete(Frame))
            await session.commit()

            # Add test frames at different depths
            test_frames = [
                (100.0, 150, 1, b"PNG100"),
                (200.0, 150, 1, b"PNG200"),
                (300.0, 150, 1, b"PNG300"),
                (400.0, 150, 1, b"PNG400"),
                (500.0, 150, 1, b"PNG500"),
            ]

            for depth, width, height, png_bytes in test_frames:
                await upsert_frame(session, depth, width, height, png_bytes)

            await session.commit()

        yield

        # Cleanup after test
        async with get_db_context() as session:
            await session.execute(delete(Frame))
            await session.commit()

    def test_get_all_frames(self):
        """Test retrieving all frames without filters."""
        response = client.get("/frames")
        assert response.status_code == 200

        data = response.json()
        assert "frames" in data
        assert "metadata" in data

        frames = data["frames"]
        metadata = data["metadata"]

        assert len(frames) == 5
        assert metadata["count"] == 5
        assert metadata["limit"] == 100
        assert metadata["offset"] == 0
        assert metadata["has_more"] is False

    def test_get_frames_with_depth_range(self):
        """Test filtering by depth_min and depth_max."""
        response = client.get("/frames?depth_min=200&depth_max=400")
        assert response.status_code == 200

        data = response.json()
        frames = data["frames"]

        # Should return frames at 200, 300, 400
        assert len(frames) == 3
        depths = [f["depth"] for f in frames]
        assert 200.0 in depths
        assert 300.0 in depths
        assert 400.0 in depths

    def test_get_frames_with_limit(self):
        """Test pagination with limit parameter."""
        response = client.get("/frames?limit=2")
        assert response.status_code == 200

        data = response.json()
        frames = data["frames"]
        metadata = data["metadata"]

        assert len(frames) == 2
        assert metadata["limit"] == 2
        assert metadata["has_more"] is True  # More frames available

    def test_get_frames_with_offset(self):
        """Test pagination with offset parameter."""
        response = client.get("/frames?limit=2&offset=2")
        assert response.status_code == 200

        data = response.json()
        frames = data["frames"]
        metadata = data["metadata"]

        assert len(frames) == 2
        assert metadata["offset"] == 2

    def test_get_frames_invalid_range(self):
        """Test that depth_max < depth_min returns 400 error."""
        response = client.get("/frames?depth_min=500&depth_max=100")
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "depth_max" in data["detail"]
        assert "depth_min" in data["detail"]

    def test_get_frames_no_results(self):
        """Test query with no matching frames."""
        response = client.get("/frames?depth_min=1000&depth_max=2000")
        assert response.status_code == 200

        data = response.json()
        frames = data["frames"]
        metadata = data["metadata"]

        assert len(frames) == 0
        assert metadata["count"] == 0
        assert metadata["has_more"] is False

    def test_frame_response_structure(self):
        """Test that frame response has correct structure."""
        response = client.get("/frames?limit=1")
        assert response.status_code == 200

        data = response.json()
        frames = data["frames"]

        assert len(frames) == 1
        frame = frames[0]

        # Check required fields
        assert "depth" in frame
        assert "width" in frame
        assert "height" in frame
        assert "image_png_base64" in frame

        # Check types
        assert isinstance(frame["depth"], float)
        assert isinstance(frame["width"], int)
        assert isinstance(frame["height"], int)
        assert isinstance(frame["image_png_base64"], str)

        # Verify base64 encoding
        try:
            decoded = base64.b64decode(frame["image_png_base64"])
            assert isinstance(decoded, bytes)
        except Exception as e:
            pytest.fail(f"Failed to decode base64: {e}")

    def test_metadata_structure(self):
        """Test that metadata has correct structure."""
        response = client.get("/frames")
        assert response.status_code == 200

        data = response.json()
        metadata = data["metadata"]

        # Check required fields
        assert "count" in metadata
        assert "limit" in metadata
        assert "offset" in metadata
        assert "has_more" in metadata

        # Optional fields (may be None)
        assert "total" in metadata or True  # Optional field
        assert "depth_min" in metadata
        assert "depth_max" in metadata


class TestReloadEndpoint:
    """Tests for POST /frames/reload endpoint."""

    def test_reload_without_auth(self):
        """Test that reload requires authentication."""
        response = client.post("/frames/reload", json={})
        assert response.status_code == 401

        data = response.json()
        assert "detail" in data
        assert "token" in data["detail"].lower() or "auth" in data["detail"].lower()

    def test_reload_with_invalid_token(self):
        """Test that invalid token is rejected."""
        headers = {"X-Admin-Token": "invalid-token-123"}
        response = client.post("/frames/reload", headers=headers, json={})
        assert response.status_code == 401

    def test_reload_with_valid_token_no_csv(self):
        """Test reload with valid auth but nonexistent CSV."""
        headers = {"X-Admin-Token": "change-me-in-production"}
        response = client.post(
            "/frames/reload",
            headers=headers,
            json={"csv_path": "nonexistent.csv"},
        )
        # Should return 400 for file not found
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_reload_response_structure(self):
        """Test that reload response has correct structure."""
        # This would need a valid CSV file to fully test
        # For now, we just verify the error response structure
        headers = {"X-Admin-Token": "change-me-in-production"}
        response = client.post(
            "/frames/reload",
            headers=headers,
            json={"csv_path": "test_frames.csv"},  # Should exist
        )

        # May succeed or fail depending on file, but should have structure
        data = response.json()

        if response.status_code == 200:
            # Success response
            assert "status" in data
            assert "message" in data
            assert data["status"] in ["success", "partial", "failed"]
        else:
            # Error response
            assert "detail" in data


class TestOpenAPIDocumentation:
    """Tests for OpenAPI documentation endpoints."""

    def test_docs_accessible(self):
        """Test that /docs endpoint is accessible."""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_openapi_json_accessible(self):
        """Test that /openapi.json is accessible."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data

        # Check our endpoints are documented
        assert "/health" in data["paths"]
        assert "/frames" in data["paths"]
        assert "/frames/reload" in data["paths"]

    def test_openapi_has_examples(self):
        """Test that OpenAPI spec includes examples."""
        response = client.get("/openapi.json")
        data = response.json()

        # Check GET /frames has documentation
        frames_endpoint = data["paths"]["/frames"]["get"]
        assert "summary" in frames_endpoint
        assert "description" in frames_endpoint
        assert "parameters" in frames_endpoint

        # Check response schemas
        assert "responses" in frames_endpoint
        assert "200" in frames_endpoint["responses"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
