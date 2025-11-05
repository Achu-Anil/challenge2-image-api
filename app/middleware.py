"""
FastAPI middleware for request tracking and logging.

This module provides middleware to inject request IDs into each request
for distributed tracing and correlation across logs.
"""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core import get_logger, set_request_id

logger = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to generate and track request IDs across the application.
    
    For each incoming request:
    1. Extracts or generates a unique request ID
    2. Sets it in context for structured logging
    3. Adds it to response headers for client-side tracing
    4. Logs request/response details with timing
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process each request with correlation ID tracking.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler
        
        Returns:
            HTTP response with X-Request-ID header
        """
        # Extract or generate request ID
        request_id = request.headers.get("X-Request-ID")
        request_id = set_request_id(request_id)

        # Record request start time
        start_time = time.time()

        # Log incoming request
        logger.info(
            "Incoming request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.query_params),
                "client_host": request.client.host if request.client else None,
            },
        )

        # Process request
        try:
            response = await call_next(request)
        except Exception as exc:
            # Log exception with request context
            logger.error(
                "Request failed with exception",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                },
                exc_info=True,
            )
            raise

        # Calculate request duration
        duration_ms = (time.time() - start_time) * 1000

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        # Log response
        logger.info(
            "Request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )

        return response
