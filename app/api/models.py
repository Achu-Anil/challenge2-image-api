"""
Pydantic models for API request/response validation.

This module defines all data models used in the API layer, including:
- Request query parameters with validation
- Response models with documentation
- Error response models
"""

import base64
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FramesQueryParams(BaseModel):
    """
    Query parameters for GET /frames endpoint.

    Provides filtering by depth range and pagination control.
    """

    depth_min: Optional[float] = Field(
        default=None,
        description="Minimum depth value (inclusive). If omitted, no lower bound.",
        examples=[0.0, 100.5, 1000.0],
        ge=0.0,  # Must be non-negative
    )

    depth_max: Optional[float] = Field(
        default=None,
        description="Maximum depth value (inclusive). If omitted, no upper bound.",
        examples=[500.0, 1500.5, 10000.0],
        ge=0.0,  # Must be non-negative
    )

    limit: int = Field(
        default=100,
        description="Maximum number of frames to return. Default: 100, Max: 1000.",
        examples=[10, 50, 100, 500],
        ge=1,  # At least 1
        le=1000,  # Maximum 1000 to prevent overload
    )

    offset: int = Field(
        default=0,
        description="Number of frames to skip for pagination. Default: 0.",
        examples=[0, 100, 200],
        ge=0,  # Cannot be negative
    )

    @field_validator("depth_max")
    @classmethod
    def validate_depth_range(cls, v: Optional[float], info) -> Optional[float]:
        """
        Validate that depth_max >= depth_min if both are provided.

        Raises:
            ValueError: If depth_max < depth_min
        """
        if v is not None and info.data.get("depth_min") is not None:
            if v < info.data["depth_min"]:
                raise ValueError(f"depth_max ({v}) must be >= depth_min ({info.data['depth_min']})")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "depth_min": 100.0,
                    "depth_max": 500.0,
                    "limit": 50,
                    "offset": 0,
                },
                {
                    "depth_min": None,
                    "depth_max": 1000.0,
                    "limit": 100,
                    "offset": 0,
                },
            ]
        }
    )


class FrameResponse(BaseModel):
    """
    Response model for a single frame.

    Contains all frame metadata and the image encoded as base64.
    """

    depth: float = Field(
        description="Depth value (primary key) for this frame",
        examples=[123.45, 567.89],
    )

    width: int = Field(
        description="Image width in pixels",
        examples=[150, 200],
        ge=1,
    )

    height: int = Field(
        description="Image height in pixels (always 1 for single-row images)",
        examples=[1],
        ge=1,
    )

    image_png_base64: str = Field(
        description=(
            "PNG image data encoded as base64 string. "
            "Decode with base64.b64decode() to get raw PNG bytes."
        ),
        examples=["iVBORw0KGgoAAAANSUhEUgAA...truncated...SUVORK5CYII="],
    )

    @field_validator("image_png_base64", mode="before")
    @classmethod
    def encode_png_to_base64(cls, v: bytes | bytearray | memoryview | str) -> str:
        """
        Convert PNG bytes to base64 string if needed.

        Args:
            v: PNG bytes (or similar binary type) or already-encoded base64 string

        Returns:
            Base64-encoded string
        """
        if isinstance(v, (bytes, bytearray, memoryview)):
            return base64.b64encode(v).decode("utf-8")
        return str(v)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "depth": 123.45,
                    "width": 150,
                    "height": 1,
                    "image_png_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                }
            ]
        }
    )


class FrameListMetadata(BaseModel):
    """
    Metadata about the frame list response.

    Provides information about pagination and total available frames.
    """

    count: int = Field(
        description="Number of frames returned in this response",
        examples=[50, 100],
        ge=0,
    )

    total: Optional[int] = Field(
        default=None,
        description="Total number of frames matching the query (if available)",
        examples=[500, 1000],
        ge=0,
    )

    depth_min: Optional[float] = Field(
        default=None,
        description="Minimum depth in the result set",
        examples=[100.0, 123.45],
    )

    depth_max: Optional[float] = Field(
        default=None,
        description="Maximum depth in the result set",
        examples=[500.0, 987.65],
    )

    limit: int = Field(
        description="Limit parameter used for this query",
        examples=[100],
        ge=1,
    )

    offset: int = Field(
        description="Offset parameter used for this query",
        examples=[0, 100],
        ge=0,
    )

    has_more: bool = Field(
        description="True if more frames are available beyond this page",
        examples=[True, False],
    )


class FrameListResponse(BaseModel):
    """
    Response model for GET /frames endpoint.

    Contains a list of frames and metadata about the result set.
    """

    frames: List[FrameResponse] = Field(
        description="List of frame objects matching the query",
        default_factory=list,
    )

    metadata: FrameListMetadata = Field(
        description="Metadata about the response (count, pagination, etc.)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "frames": [
                        {
                            "depth": 123.45,
                            "width": 150,
                            "height": 1,
                            "image_png_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ...",
                        }
                    ],
                    "metadata": {
                        "count": 1,
                        "total": 100,
                        "depth_min": 123.45,
                        "depth_max": 123.45,
                        "limit": 100,
                        "offset": 0,
                        "has_more": False,
                    },
                }
            ]
        }
    )


class ReloadRequest(BaseModel):
    """
    Request model for POST /frames/reload endpoint.

    Optional parameters to control re-ingestion behavior.
    """

    csv_path: Optional[str] = Field(
        default=None,
        description="Path to CSV file to ingest. If omitted, uses default from settings.",
        examples=["data/frames.csv", "/path/to/custom.csv"],
    )

    chunk_size: Optional[int] = Field(
        default=None,
        description="Number of rows to process per batch. If omitted, uses default.",
        examples=[500, 1000],
        ge=1,
    )

    clear_existing: bool = Field(
        default=False,
        description="If true, delete all existing frames before ingesting. Default: false (upsert).",
        examples=[False, True],
    )


class ReloadResponse(BaseModel):
    """
    Response model for POST /frames/reload endpoint.

    Reports the results of the re-ingestion operation.
    """

    status: str = Field(
        description="Status of the reload operation",
        examples=["success", "failed", "partial"],
    )

    message: str = Field(
        description="Human-readable description of the result",
        examples=["Ingestion completed successfully", "Failed to read CSV file"],
    )

    rows_processed: Optional[int] = Field(
        default=None,
        description="Number of CSV rows processed",
        examples=[1000, 5000],
        ge=0,
    )

    frames_stored: Optional[int] = Field(
        default=None,
        description="Number of frames stored/updated in database",
        examples=[1000, 5000],
        ge=0,
    )

    duration_seconds: Optional[float] = Field(
        default=None,
        description="Time taken for the operation in seconds",
        examples=[15.5, 120.3],
        ge=0.0,
    )


class ErrorResponse(BaseModel):
    """
    Consistent error response model for all API errors.

    Used by exception handlers to return structured error information.
    """

    error: str = Field(
        description="Error type or category",
        examples=["ValidationError", "NotFound", "InternalServerError"],
    )

    detail: str = Field(
        description="Detailed error message",
        examples=[
            "depth_max (100.0) must be >= depth_min (200.0)",
            "No frames found in specified range",
            "Database connection failed",
        ],
    )

    error_code: Optional[str] = Field(
        default=None,
        description="Machine-readable error code for client handling",
        examples=["INVALID_RANGE", "NOT_FOUND", "DB_ERROR"],
    )

    request_id: Optional[str] = Field(
        default=None,
        description="Request ID for tracking and debugging",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )

    timestamp: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp of when the error occurred",
        examples=["2025-11-06T02:30:00Z"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": "ValidationError",
                    "detail": "depth_max (100.0) must be >= depth_min (200.0)",
                    "error_code": "INVALID_RANGE",
                    "request_id": "550e8400-e29b-41d4-a716-446655440000",
                    "timestamp": "2025-11-06T02:30:00Z",
                }
            ]
        }
    )
