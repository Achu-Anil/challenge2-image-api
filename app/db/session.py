"""
Database session management and connection handling.

This module provides async database session creation and management
using SQLAlchemy 2.0 async engine with connection pooling.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core import get_logger, settings
from app.db.models import Base

logger = get_logger(__name__)

# Global engine and session factory
_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    """
    Get or create the global async database engine.
    
    Configures connection pooling based on database type:
    - SQLite: NullPool (no connection pooling, SQLite limitation)
    - PostgreSQL: QueuePool with sensible defaults
    
    Returns:
        Configured async SQLAlchemy engine
    """
    global _engine

    if _engine is not None:
        return _engine

    # Engine configuration for SQLite with async support
    engine_kwargs = {
        "url": settings.database_url,
        "poolclass": NullPool,  # Required for SQLite
        "echo": settings.log_level == "DEBUG",  # Log SQL in debug mode
        "connect_args": {"check_same_thread": False},  # Required for SQLite async
    }

    _engine = create_async_engine(**engine_kwargs)
    logger.info(
        "Database engine created",
        extra={
            "database_type": "SQLite",
            "pool_class": "NullPool",
        },
    )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Get or create the global async session factory.
    
    Returns:
        Configured async session maker
    """
    global _async_session_factory

    if _async_session_factory is not None:
        return _async_session_factory

    engine = get_engine()
    _async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,  # Prevent lazy loading errors
        autoflush=False,  # Manual flush for better control
        autocommit=False,  # Explicit transaction management
    )

    logger.info("Database session factory created")
    return _async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function to get a database session.
    
    Use this as a FastAPI dependency to inject database sessions into endpoints:
    
    Example:
        @app.get("/frames")
        async def get_frames(db: AsyncSession = Depends(get_db)):
            # Use db session here
            pass
    
    Yields:
        Async database session
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions outside of FastAPI dependencies.
    
    Use this in scripts or background tasks:
    
    Example:
        async with get_db_context() as db:
            # Use db session here
            pass
    
    Yields:
        Async database session
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize the database by creating all tables.
    
    Creates tables defined in SQLAlchemy models if they don't exist.
    Idempotent operation - safe to call multiple times.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized")


async def close_db() -> None:
    """
    Close database connections and dispose of the engine.
    
    Call this during application shutdown to gracefully close connections.
    """
    global _engine, _async_session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("Database connections closed")
