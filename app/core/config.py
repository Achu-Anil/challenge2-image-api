"""
Core application configuration using Pydantic Settings.

This module provides a centralized configuration management system using environment variables.
Settings can be overridden via .env file or system environment variables.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Attributes:
        database_url: SQLAlchemy database connection string
        app_name: Application name for logging and OpenAPI
        app_version: Semantic version string
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        environment: Runtime environment (development, staging, production)
        api_host: Host to bind the API server
        api_port: Port to bind the API server
        api_reload: Enable auto-reload on code changes (dev only)
        csv_file_path: Path to the input CSV file for ingestion
        chunk_size: Number of rows to process in each batch during ingestion
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database configuration
    database_url: str = Field(
        default="sqlite+aiosqlite:///./frames.db",
        description="Database connection URL (supports PostgreSQL and SQLite)",
    )

    # Application metadata
    app_name: str = Field(default="ImageFramesAPI", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )
    environment: Literal["development", "staging", "production"] = Field(
        default="development", description="Runtime environment"
    )

    # API server settings
    api_host: str = Field(default="0.0.0.0", description="API host binding")
    api_port: int = Field(default=8000, ge=1024, le=65535, description="API port binding")
    api_reload: bool = Field(default=True, description="Enable auto-reload for development")

    # Ingestion settings
    csv_file_path: str = Field(
        default="./data/frames.csv", description="Path to CSV file for ingestion"
    )
    chunk_size: int = Field(
        default=500, ge=1, le=10000, description="Batch size for CSV processing"
    )
    
    # Security settings
    admin_token: str = Field(
        default="change-me-in-production",
        description="Admin token for secured endpoints (e.g., /frames/reload)",
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate that database URL uses supported drivers."""
        supported_dialects = ["postgresql+asyncpg", "sqlite+aiosqlite"]
        if not any(v.startswith(dialect) for dialect in supported_dialects):
            raise ValueError(
                f"Database URL must start with one of: {', '.join(supported_dialects)}"
            )
        return v

    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite database."""
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL database."""
        return self.database_url.startswith("postgresql")

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"


@lru_cache()
def get_settings() -> Settings:
    """
    Create and cache application settings instance.
    
    Uses LRU cache to ensure only one Settings instance is created,
    following the singleton pattern for configuration.
    
    Returns:
        Cached Settings instance
    """
    return Settings()


# Convenience export for direct import
settings = get_settings()
