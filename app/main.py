"""
Image Frames API - Main application entry point.

This FastAPI application processes and serves depth-keyed grayscale image frames
with custom colorization. Think of it as Instagram filters for geological data! 🎨

Features include:
- Async database operations with SQLAlchemy (because blocking I/O is so 2010)
- Structured JSON logging with request ID tracking (your logs, but make it fashion ✨)
- Health check endpoints (yes, we're alive and well, thank you for asking)
- OpenAPI/Swagger documentation (interactive API docs that actually work!)

Architecture:
    CSV → Pandas → NumPy → Colormap → PNG → SQLite → FastAPI → Your Browser
    
    It's like a data pipeline, but with more colors and fewer tears.
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
# (Yes, we log in JSON. No, we're not sorry. Machines > humans for parsing logs)
setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan manager for startup and shutdown events.
    
    This is like the application's morning coffee and evening wind-down routine.
    We wake up, stretch our database connections, and get ready for the day.
    At night, we tidy up, close connections, and go to sleep peacefully. 😴
    
    Startup sequence:
        1. Initialize database tables (CREATE TABLE IF NOT EXISTS...)
        2. Log application configuration (because visibility is key)
        3. Warm up connection pools (database connections, assemble!)
    
    Shutdown sequence:
        1. Close database connections (goodbye, old friends)
        2. Cleanup resources (leave no trace)
        3. Log final metrics (how did we do today?)
    
    Args:
        app: FastAPI application instance (the star of the show)
    
    Yields:
        Control to the application (do your thing, FastAPI!)
    """
    # ========================================
    # Startup: Rise and shine! ☀️
    # ========================================
    logger.info(
        "Application starting",
        extra={
            "app_name": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "database_type": "PostgreSQL" if settings.is_postgres else "SQLite",
        },
    )

    # Initialize database (create tables if they don't exist)
    # Fun fact: This is idempotent, so it's safe to run multiple times
    await init_db()
    logger.info("Database initialized")

    # Hand control back to FastAPI
    # (This is where the magic happens - FastAPI handles all the requests)
    yield

    # ========================================
    # Shutdown: Time to go home! 🌙
    # ========================================
    logger.info("Application shutting down")
    
    # Close database connections gracefully
    # (Because manners matter, even for databases)
    await close_db()
    logger.info("Application shutdown complete")


# ============================================================================
# FastAPI Application Configuration
# ============================================================================
# Create our main FastAPI app with all the bells and whistles.
# It's like building a house: we need a good foundation (FastAPI),
# proper plumbing (database), electricity (logging), and a nice paint job (docs).

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Process and serve depth-keyed grayscale image frames with custom colorization. "
        "Handles CSV ingestion, image resizing, color mapping, and efficient frame retrieval. "
        "\n\n"
        "Think of it as a magical rainbow machine that turns boring grayscale numbers "
        "into beautiful color-coded visualizations! 🌈"
    ),
    lifespan=lifespan,  # Our startup/shutdown choreographer
    default_response_class=ORJSONResponse,  # Fast JSON (orjson is 2-3x faster than stdlib json!)
    docs_url="/docs",  # Swagger UI (interactive API docs)
    redoc_url="/redoc",  # ReDoc (alternative, prettier docs)
    openapi_url="/openapi.json",  # OpenAPI schema (for code generation, etc.)
)

# ============================================================================
# Middleware Stack
# ============================================================================
# Add middleware for request ID tracking
# This injects a unique ID into every request, making debugging a breeze!
# Instead of "which request failed?", you can say "request abc-123 failed"
app.add_middleware(RequestIDMiddleware)

# ============================================================================
# Router Registration
# ============================================================================
# Include all our API routes
# (health checks, frame queries, cache management, etc.)
app.include_router(router, tags=["health"])

# ============================================================================
# Root Endpoint
# ============================================================================
@app.get("/", tags=["root"])
async def root() -> dict:
    """
    Root endpoint with API information.
    
    This is the "Hello World" of our API - a friendly welcome message
    with directions to the good stuff (docs, health checks, etc.)
    
    Returns:
        dict: Welcome message and links to important endpoints
        
    Example:
        ```
        GET /
        {
          "message": "Welcome to ImageFramesAPI",
          "version": "0.1.0",
          "docs": "/docs",
          "health": "/health"
        }
        ```
    """
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs",  # Your interactive API playground
        "health": "/health",  # Quick health check
    }


# ============================================================================
# Development Server Entry Point
# ============================================================================
# This block runs when you execute `python -m app.main` directly.
# For production, you'd use something like:
#   uvicorn app.main:app --workers 4 --host 0.0.0.0 --port 8000
#
# But for development? This is your friend. Auto-reload on code changes! 🔄

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

    # Fire up uvicorn with all the development niceties
    uvicorn.run(
        "app.main:app",  # Import string (not the app object itself - needed for reload)
        host=settings.api_host,  # Bind to all interfaces (0.0.0.0) or localhost
        port=settings.api_port,  # Default: 8000
        reload=settings.api_reload,  # Auto-reload on code changes (dev only!)
        log_level=settings.log_level.lower(),  # uvicorn wants lowercase log levels
    )
