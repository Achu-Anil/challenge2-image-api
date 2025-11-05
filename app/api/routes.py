"""
API route handlers.

This module defines all API endpoints for the Image Frames API.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_logger, settings
from app.db import get_db

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
