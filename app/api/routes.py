"""
API route handlers.

This module defines all API endpoints for the Image Frames API.

Endpoints:
- GET /health: Health check with database connectivity test
- GET /frames: Retrieve frames by depth range with pagination
- POST /frames/reload: Admin endpoint to trigger re-ingestion (secured)
"""

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.models import (
    FrameResponse,
    FrameListResponse,
    FrameListMetadata,
    FramesQueryParams,
    ReloadRequest,
    ReloadResponse,
    ErrorResponse,
)
from app.core import get_logger, settings
from app.db import get_db, Frame
from app.db.operations import (
    get_frames_by_depth_range,
    count_frames,
    get_depth_range,
)

logger = get_logger(__name__)

# Create API router
router = APIRouter()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Health check endpoint to verify API and database connectivity.
    
    Returns:
        dict: Health status with application metadata
    
    Example response:
        {
            "status": "healthy",
            "app_name": "ImageFramesAPI",
            "version": "0.1.0",
            "environment": "development",
            "database": "connected"
        }
    """
    # Test database connection
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.error("Database health check failed", extra={"error": str(e)})
        db_status = "disconnected"

    response = {
        "status": "healthy" if db_status == "connected" else "degraded",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "database": db_status,
    }

    logger.debug("Health check performed", extra=response)
    return response


@router.get(
    "/frames",
    response_model=FrameListResponse,
    summary="Get frames by depth range",
    description="""
    Retrieve image frames within a specified depth range.
    
    **Filtering:**
    - Use `depth_min` and/or `depth_max` to filter by depth range
    - Both parameters are inclusive and optional
    - If neither is provided, returns all frames (subject to limit)
    
    **Pagination:**
    - `limit`: Maximum frames to return (default: 100, max: 1000)
    - `offset`: Number of frames to skip (default: 0)
    - Use `metadata.has_more` to check if more results are available
    
    **Response:**
    - Each frame includes depth, dimensions, and base64-encoded PNG image
    - Use `base64.b64decode()` to convert image_png_base64 to raw PNG bytes
    - Metadata includes count, total, depth range, and pagination info
    
    **Example queries:**
    - All frames: `GET /frames`
    - Specific range: `GET /frames?depth_min=100&depth_max=500`
    - Pagination: `GET /frames?limit=50&offset=100`
    """,
    responses={
        200: {
            "description": "Successfully retrieved frames",
            "model": FrameListResponse,
        },
        400: {
            "description": "Invalid query parameters (e.g., depth_max < depth_min)",
            "model": ErrorResponse,
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse,
        },
    },
    tags=["frames"],
)
async def get_frames(
    depth_min: Optional[float] = Query(
        default=None,
        description="Minimum depth value (inclusive)",
        examples=[0.0, 100.0],
        ge=0.0,
    ),
    depth_max: Optional[float] = Query(
        default=None,
        description="Maximum depth value (inclusive)",
        examples=[500.0, 1000.0],
        ge=0.0,
    ),
    limit: int = Query(
        default=100,
        description="Maximum number of frames to return",
        examples=[50, 100],
        ge=1,
        le=1000,
    ),
    offset: int = Query(
        default=0,
        description="Number of frames to skip",
        examples=[0, 100],
        ge=0,
    ),
    db: AsyncSession = Depends(get_db),
) -> FrameListResponse:
    """
    Get frames within a depth range with pagination.
    
    Args:
        depth_min: Minimum depth (inclusive), optional
        depth_max: Maximum depth (inclusive), optional
        limit: Max frames to return (1-1000)
        offset: Number of frames to skip
        db: Database session (injected)
    
    Returns:
        FrameListResponse with frames and metadata
        
    Raises:
        HTTPException: 400 if depth_max < depth_min
        HTTPException: 500 if database error occurs
    """
    start_time = time.time()
    
    # Validate depth range
    if depth_min is not None and depth_max is not None and depth_max < depth_min:
        logger.warning(
            "Invalid depth range requested",
            extra={"depth_min": depth_min, "depth_max": depth_max},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"depth_max ({depth_max}) must be >= depth_min ({depth_min})",
        )
    
    try:
        # Query frames with limit+1 to check if more results exist
        frames_list = await get_frames_by_depth_range(
            session=db,
            depth_min=depth_min,
            depth_max=depth_max,
            limit=limit + 1,  # Fetch one extra to detect has_more
            offset=offset,
        )
        
        # Check if more results are available
        has_more = len(frames_list) > limit
        if has_more:
            frames_list = frames_list[:limit]  # Trim to requested limit
        
        # Convert Frame ORM objects to FrameResponse models
        frame_responses = [
            FrameResponse(
                depth=frame.depth,
                width=frame.width,
                height=frame.height,
                image_png_base64=frame.image_png,  # type: ignore  # Validator will encode bytes to base64
            )
            for frame in frames_list
        ]
        
        # Calculate metadata
        count = len(frame_responses)
        
        # Get actual depth range from results (not query params)
        result_depth_min = None
        result_depth_max = None
        if frame_responses:
            result_depth_min = min(f.depth for f in frame_responses)
            result_depth_max = max(f.depth for f in frame_responses)
        
        # Get total count (expensive, so we skip it for now)
        # Could be optimized with a separate count query or caching
        total = None
        
        metadata = FrameListMetadata(
            count=count,
            total=total,
            depth_min=result_depth_min,
            depth_max=result_depth_max,
            limit=limit,
            offset=offset,
            has_more=has_more,
        )
        
        duration = time.time() - start_time
        logger.info(
            "Frames retrieved",
            extra={
                "count": count,
                "depth_min_param": depth_min,
                "depth_max_param": depth_max,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "duration_ms": round(duration * 1000, 2),
            },
        )
        
        return FrameListResponse(frames=frame_responses, metadata=metadata)
        
    except HTTPException:
        # Re-raise HTTP exceptions (like validation errors)
        raise
    except Exception as e:
        logger.exception(
            "Error retrieving frames",
            extra={
                "depth_min": depth_min,
                "depth_max": depth_max,
                "limit": limit,
                "offset": offset,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve frames: {str(e)}",
        )


@router.post(
    "/frames/reload",
    response_model=ReloadResponse,
    summary="Reload frames from CSV (Admin only)",
    description="""
    Trigger re-ingestion of frames from CSV file.
    
    **Authentication:**
    - Requires `X-Admin-Token` header matching configured admin token
    - Returns 401 Unauthorized if token is missing or invalid
    
    **Parameters:**
    - `csv_path`: Optional path to CSV file (uses default if omitted)
    - `chunk_size`: Optional batch size for processing
    - `clear_existing`: If true, deletes all frames before ingesting
    
    **Behavior:**
    - By default, performs idempotent upsert (safe to re-run)
    - If `clear_existing=true`, truncates frames table first
    - Runs ingestion synchronously (blocks until complete)
    
    **Response:**
    - Status: "success", "failed", or "partial"
    - Includes metrics: rows processed, frames stored, duration
    
    **Use cases:**
    - Reload data after CSV updates
    - Re-process with different parameters
    - Clear and rebuild database
    """,
    responses={
        200: {
            "description": "Ingestion completed successfully",
            "model": ReloadResponse,
        },
        401: {
            "description": "Missing or invalid admin token",
            "model": ErrorResponse,
        },
        400: {
            "description": "Invalid request parameters",
            "model": ErrorResponse,
        },
        500: {
            "description": "Ingestion failed",
            "model": ErrorResponse,
        },
    },
    tags=["admin"],
)
async def reload_frames(
    request: ReloadRequest,
    db: AsyncSession = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> ReloadResponse:
    """
    Reload frames from CSV (admin endpoint, requires auth).
    
    Args:
        request: Reload parameters (csv_path, chunk_size, clear_existing)
        db: Database session (injected)
        x_admin_token: Admin token from X-Admin-Token header
    
    Returns:
        ReloadResponse with status and metrics
        
    Raises:
        HTTPException: 401 if auth fails
        HTTPException: 400 if request is invalid
        HTTPException: 500 if ingestion fails
    """
    start_time = time.time()
    
    # Authentication check
    expected_token = settings.admin_token
    if not expected_token or x_admin_token != expected_token:
        logger.warning(
            "Unauthorized reload attempt",
            extra={"token_provided": bool(x_admin_token)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Admin-Token header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info(
        "Reload request received",
        extra={
            "csv_path": request.csv_path,
            "chunk_size": request.chunk_size,
            "clear_existing": request.clear_existing,
        },
    )
    
    try:
        # Clear existing frames if requested
        if request.clear_existing:
            from sqlalchemy import delete
            await db.execute(delete(Frame))
            await db.commit()
            logger.info("Cleared all existing frames")
        
        # Determine CSV path and chunk size
        from pathlib import Path
        csv_path = Path(request.csv_path) if request.csv_path else Path(settings.csv_file_path)
        chunk_size = request.chunk_size if request.chunk_size else settings.chunk_size
        
        if not csv_path.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV file not found: {csv_path}",
            )
        
        # Run ingestion (import here to avoid circular dependency)
        from app.processing.ingest import ingest_csv
        
        result = await ingest_csv(
            csv_path=csv_path,
            chunk_size=chunk_size,
            source_width=200,  # Could be made configurable
            target_width=150,  # Could be made configurable
        )
        
        duration = time.time() - start_time
        
        # Check if ingestion was successful
        if result["rows_processed"] == result["frames_upserted"]:
            status_str = "success"
            message = f"Successfully ingested {result['frames_upserted']} frames"
        else:
            status_str = "partial"
            message = (
                f"Processed {result['rows_processed']} rows but only "
                f"stored {result['frames_upserted']} frames (some rows failed)"
            )
        
        logger.info(
            "Reload completed",
            extra={
                "status": status_str,
                "rows_processed": result["rows_processed"],
                "frames_stored": result["frames_upserted"],
                "duration_seconds": duration,
            },
        )
        
        return ReloadResponse(
            status=status_str,
            message=message,
            rows_processed=result["rows_processed"],
            frames_stored=result["frames_upserted"],
            duration_seconds=duration,
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.exception("Reload failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reload failed: {str(e)}",
        )
