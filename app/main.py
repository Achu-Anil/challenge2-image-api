"""
Image Frames API - Main application entry point.

This FastAPI application processes and serves depth-keyed grayscale image frames
with custom colorization. Features include:
- Async database operations with SQLAlchemy
- Structured JSON logging with request ID tracking
- Health check endpoints
- OpenAPI/Swagger documentation
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import orjson
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.api import router
from app.core import get_logger, settings, setup_logging
from app.db import close_db, init_db
from app.middleware import RequestIDMiddleware

# Initialize structured logging
setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan manager for startup and shutdown events.
    
    Startup:
        - Initialize database tables
        - Log application configuration
    
    Shutdown:
        - Close database connections
        - Cleanup resources
    
    Args:
        app: FastAPI application instance
    
    Yields:
        Control to the application
    """
    # Startup
    logger.info(
        "Application starting",
        extra={
            "app_name": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "database_type": "PostgreSQL" if settings.is_postgres else "SQLite",
        },
    )

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Application shutting down")
    await close_db()
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Process and serve depth-keyed grayscale image frames with custom colorization. "
        "Handles CSV ingestion, image resizing, color mapping, and efficient frame retrieval."
    ),
    lifespan=lifespan,
    default_response_class=ORJSONResponse,  # Fast JSON serialization
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Add middleware
app.add_middleware(RequestIDMiddleware)

# Include routers
app.include_router(router, tags=["health"])

# Root endpoint
@app.get("/", tags=["root"])
async def root() -> dict:
    """
    Root endpoint with API information.
    
    Returns:
        dict: Welcome message and API details
    """
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    logger.info(
        "Starting development server",
        extra={
            "host": settings.api_host,
            "port": settings.api_port,
            "reload": settings.api_reload,
        },
    )

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )
