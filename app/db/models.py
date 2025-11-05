"""
SQLAlchemy database models for the Image Frames API.

This module defines the database schema using SQLAlchemy 2.0 async ORM.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import LargeBinary, Float, Integer, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class Frame(Base):
    """
    Image frame model storing processed depth-keyed images.
    
    Each frame represents a single row from the CSV file that has been:
    1. Resized from 200 to 150 pixels width
    2. Colorized using a custom color map
    3. Encoded as PNG binary data
    
    Attributes:
        depth: Depth value (primary key, unique identifier for each frame)
        image_png: PNG-encoded image binary data
        width: Image width in pixels (should be 150 after processing)
        height: Image height in pixels (should be 1 for single-row images)
        created_at: Timestamp when the frame was first created
        updated_at: Timestamp when the frame was last updated
    """

    __tablename__ = "frames"

    # Primary key: depth value from CSV
    depth: Mapped[float] = mapped_column(
        Float,
        primary_key=True,
        index=True,
        doc="Depth value from CSV (primary key)",
    )

    # Image data
    image_png: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
        doc="PNG-encoded image binary data",
    )

    # Image dimensions
    width: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Image width in pixels (150 after resize)",
    )

    height: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Image height in pixels (1 for single-row images)",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when frame was created",
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        doc="Timestamp when frame was last updated",
    )

    def __repr__(self) -> str:
        """String representation of Frame for debugging."""
        return (
            f"<Frame(depth={self.depth}, "
            f"dimensions={self.width}x{self.height}, "
            f"size={len(self.image_png)} bytes)>"
        )

    def to_dict(self) -> dict:
        """
        Convert frame to dictionary representation.
        
        Note: image_png is excluded to avoid large binary data in logs.
        Use this for API responses with explicit image handling.
        
        Returns:
            Dictionary with frame metadata (excluding binary image data)
        """
        return {
            "depth": self.depth,
            "width": self.width,
            "height": self.height,
            "image_size_bytes": len(self.image_png),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
