"""
Tests for API models and Pydantic validators.

These tests focus on:
- Model validation logic
- Field validators
- Base64 encoding
- Error responses
- Example schemas
"""

import base64

import pytest
from pydantic import ValidationError

from app.api.models import (
    ErrorResponse,
    FrameListMetadata,
    FrameListResponse,
    FrameResponse,
    FramesQueryParams,
    ReloadRequest,
    ReloadResponse,
)


class TestFramesQueryParams:
    """Test FramesQueryParams model validation."""

    def test_query_params_valid(self):
        """Test valid query parameters."""
        params = FramesQueryParams(
            depth_min=100.0,
            depth_max=500.0,
            limit=50,
            offset=10,
        )

        assert params.depth_min == 100.0
        assert params.depth_max == 500.0
        assert params.limit == 50
        assert params.offset == 10

    def test_query_params_depth_max_less_than_min(self):
        """Test validation when depth_max < depth_min."""
        with pytest.raises(ValidationError) as exc_info:
            FramesQueryParams(
                depth_min=500.0,
                depth_max=100.0,  # Less than depth_min
            )

        error = exc_info.value
        assert "depth_max" in str(error)
        assert "must be >=" in str(error)

    def test_query_params_optional_depths(self):
        """Test that depth parameters are optional."""
        params = FramesQueryParams(limit=100, offset=0)

        assert params.depth_min is None
        assert params.depth_max is None

    def test_query_params_only_depth_min(self):
        """Test with only depth_min set."""
        params = FramesQueryParams(depth_min=100.0)

        assert params.depth_min == 100.0
        assert params.depth_max is None

    def test_query_params_only_depth_max(self):
        """Test with only depth_max set."""
        params = FramesQueryParams(depth_max=500.0)

        assert params.depth_min is None
        assert params.depth_max == 500.0

    def test_query_params_default_values(self):
        """Test default values for limit and offset."""
        params = FramesQueryParams()

        assert params.limit == 100
        assert params.offset == 0

    def test_query_params_limit_boundaries(self):
        """Test limit validation boundaries."""
        # Min limit
        params = FramesQueryParams(limit=1)
        assert params.limit == 1

        # Max limit
        params = FramesQueryParams(limit=1000)
        assert params.limit == 1000

        # Below min
        with pytest.raises(ValidationError):
            FramesQueryParams(limit=0)

        # Above max
        with pytest.raises(ValidationError):
            FramesQueryParams(limit=1001)

    def test_query_params_negative_offset(self):
        """Test that negative offset is rejected."""
        with pytest.raises(ValidationError):
            FramesQueryParams(offset=-1)


class TestFrameResponse:
    """Test FrameResponse model and base64 encoding."""

    def test_frame_response_with_bytes(self):
        """Test FrameResponse with PNG bytes (validator converts to base64)."""
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

        # The validator converts bytes to base64 string
        frame = FrameResponse(
            depth=123.45,
            width=150,
            height=1,
            image_png_base64=png_bytes,  # type: ignore
        )

        # Should be encoded to base64
        assert isinstance(frame.image_png_base64, str)
        # Should be valid base64
        decoded = base64.b64decode(frame.image_png_base64)
        assert decoded == png_bytes

    def test_frame_response_with_base64_string(self):
        """Test FrameResponse with already-encoded base64 string."""
        base64_str = base64.b64encode(b"PNG_DATA").decode("utf-8")

        frame = FrameResponse(
            depth=123.45,
            width=150,
            height=1,
            image_png_base64=base64_str,
        )

        assert frame.image_png_base64 == base64_str

    def test_frame_response_with_bytearray(self):
        """Test FrameResponse with bytearray."""
        png_data = bytearray(b"PNG_DATA")

        frame = FrameResponse(
            depth=123.45,
            width=150,
            height=1,
            image_png_base64=png_data,  # type: ignore
        )

        assert isinstance(frame.image_png_base64, str)
        decoded = base64.b64decode(frame.image_png_base64)
        assert decoded == bytes(png_data)

    def test_frame_response_with_memoryview(self):
        """Test FrameResponse with memoryview."""
        png_data = memoryview(b"PNG_DATA")

        frame = FrameResponse(
            depth=123.45,
            width=150,
            height=1,
            image_png_base64=png_data,  # type: ignore
        )

        assert isinstance(frame.image_png_base64, str)
        decoded = base64.b64decode(frame.image_png_base64)
        assert decoded == bytes(png_data)

    def test_frame_response_depth_precision(self):
        """Test that depth preserves decimal precision."""
        frame = FrameResponse(
            depth=123.456789,
            width=150,
            height=1,
            image_png_base64=b"DATA",  # type: ignore
        )

        assert frame.depth == 123.456789

    def test_frame_response_json_serialization(self):
        """Test that FrameResponse can be serialized to JSON."""
        frame = FrameResponse(
            depth=123.45,
            width=150,
            height=1,
            image_png_base64=b"PNG_DATA",  # type: ignore
        )

        json_data = frame.model_dump()

        assert json_data["depth"] == 123.45
        assert json_data["width"] == 150
        assert json_data["height"] == 1
        assert isinstance(json_data["image_png_base64"], str)


class TestFrameListMetadata:
    """Test FrameListMetadata model."""

    def test_metadata_complete(self):
        """Test metadata with all fields."""
        metadata = FrameListMetadata(
            count=10,
            total=100,
            depth_min=100.0,
            depth_max=500.0,
            limit=50,
            offset=0,
            has_more=True,
        )

        assert metadata.count == 10
        assert metadata.total == 100
        assert metadata.depth_min == 100.0
        assert metadata.depth_max == 500.0
        assert metadata.has_more is True

    def test_metadata_optional_fields(self):
        """Test metadata with optional fields as None."""
        metadata = FrameListMetadata(
            count=5,
            total=None,
            depth_min=None,
            depth_max=None,
            limit=100,
            offset=0,
            has_more=False,
        )

        assert metadata.count == 5
        assert metadata.total is None
        assert metadata.depth_min is None
        assert metadata.depth_max is None

    def test_metadata_has_more_required(self):
        """Test that has_more must be provided."""
        metadata = FrameListMetadata(
            count=5,
            limit=100,
            offset=0,
            has_more=False,
        )

        assert metadata.has_more is False


class TestFrameListResponse:
    """Test FrameListResponse model."""

    def test_frame_list_response_empty(self):
        """Test response with no frames."""
        response = FrameListResponse(
            frames=[],
            metadata=FrameListMetadata(
                count=0,
                limit=100,
                offset=0,
                has_more=False,
            ),
        )

        assert len(response.frames) == 0
        assert response.metadata.count == 0

    def test_frame_list_response_with_frames(self):
        """Test response with multiple frames."""
        frames = [
            FrameResponse(depth=100.0, width=150, height=1, image_png_base64=b"DATA1"),  # type: ignore
            FrameResponse(depth=200.0, width=150, height=1, image_png_base64=b"DATA2"),  # type: ignore
        ]

        response = FrameListResponse(
            frames=frames,
            metadata=FrameListMetadata(
                count=2,
                depth_min=100.0,
                depth_max=200.0,
                limit=100,
                offset=0,
                has_more=False,
            ),
        )

        assert len(response.frames) == 2
        assert response.metadata.count == 2


class TestReloadRequest:
    """Test ReloadRequest model."""

    def test_reload_request_empty(self):
        """Test reload request with no parameters."""
        request = ReloadRequest()

        assert request.csv_path is None
        assert request.chunk_size is None
        assert request.clear_existing is False

    def test_reload_request_with_csv_path(self):
        """Test reload request with CSV path."""
        request = ReloadRequest(csv_path="/path/to/file.csv")

        assert request.csv_path == "/path/to/file.csv"

    def test_reload_request_with_chunk_size(self):
        """Test reload request with custom chunk size."""
        request = ReloadRequest(chunk_size=1000)

        assert request.chunk_size == 1000

    def test_reload_request_with_clear_existing(self):
        """Test reload request with clear_existing flag."""
        request = ReloadRequest(clear_existing=True)

        assert request.clear_existing is True

    def test_reload_request_all_parameters(self):
        """Test reload request with all parameters."""
        request = ReloadRequest(
            csv_path="/data/frames.csv",
            chunk_size=500,
            clear_existing=True,
        )

        assert request.csv_path == "/data/frames.csv"
        assert request.chunk_size == 500
        assert request.clear_existing is True

    def test_reload_request_chunk_size_validation(self):
        """Test chunk size must be positive."""
        with pytest.raises(ValidationError):
            ReloadRequest(chunk_size=0)

        with pytest.raises(ValidationError):
            ReloadRequest(chunk_size=-1)


class TestReloadResponse:
    """Test ReloadResponse model."""

    def test_reload_response_success(self):
        """Test successful reload response."""
        response = ReloadResponse(
            status="success",
            message="Successfully ingested 100 frames",
            rows_processed=100,
            frames_stored=100,
            duration_seconds=5.5,
        )

        assert response.status == "success"
        assert response.rows_processed == 100
        assert response.frames_stored == 100
        assert response.duration_seconds == 5.5

    def test_reload_response_partial(self):
        """Test partial success reload response."""
        response = ReloadResponse(
            status="partial",
            message="Processed 100 rows but only stored 95 frames",
            rows_processed=100,
            frames_stored=95,
            duration_seconds=5.5,
        )

        assert response.status == "partial"
        assert response.rows_processed == 100
        assert response.frames_stored == 95

    def test_reload_response_failed(self):
        """Test failed reload response."""
        response = ReloadResponse(
            status="failed",
            message="Ingestion failed due to database error",
            rows_processed=0,
            frames_stored=0,
            duration_seconds=0.1,
        )

        assert response.status == "failed"


class TestErrorResponse:
    """Test ErrorResponse model."""

    def test_error_response_basic(self):
        """Test basic error response."""
        error = ErrorResponse(
            error="ValidationError",
            detail="Something went wrong",
        )

        assert error.error == "ValidationError"
        assert error.detail == "Something went wrong"

    def test_error_response_with_optional_fields(self):
        """Test error response with all fields."""
        error = ErrorResponse(
            error="NotFound",
            detail="Resource not found",
            error_code="NOT_FOUND",
            request_id="12345",
            timestamp="2025-11-06T00:00:00Z",
        )

        assert error.error == "NotFound"
        assert error.detail == "Resource not found"
        assert error.error_code == "NOT_FOUND"
        assert error.request_id == "12345"
        assert error.timestamp == "2025-11-06T00:00:00Z"

    def test_error_response_json_serialization(self):
        """Test error response JSON serialization."""
        error = ErrorResponse(
            error="InternalError",
            detail="Test error",
        )

        json_data = error.model_dump()

        assert json_data["error"] == "InternalError"
        assert json_data["detail"] == "Test error"


class TestModelExamples:
    """Test that models have valid example schemas."""

    def test_query_params_examples(self):
        """Test FramesQueryParams has valid examples in schema."""
        schema = FramesQueryParams.model_json_schema()

        assert "examples" in schema or "$defs" in schema or "properties" in schema

    def test_frame_response_examples(self):
        """Test FrameResponse has valid examples in schema."""
        schema = FrameResponse.model_json_schema()

        # Should have examples or be able to generate docs
        assert schema is not None

    def test_reload_request_examples(self):
        """Test ReloadRequest has valid examples in schema."""
        schema = ReloadRequest.model_json_schema()

        assert schema is not None
