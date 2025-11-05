"""Database layer exports."""

from app.db.models import Base, Frame
from app.db.operations import (
    count_frames,
    delete_frame,
    get_depth_range,
    get_frame_by_depth,
    get_frames_by_depth_range,
    upsert_frame,
    upsert_frames_batch,
)
from app.db.session import (
    close_db,
    get_db,
    get_db_context,
    get_engine,
    get_session_factory,
    init_db,
)

__all__ = [
    # Models
    "Base",
    "Frame",
    # Session management
    "get_engine",
    "get_session_factory",
    "get_db",
    "get_db_context",
    "init_db",
    "close_db",
    # Operations
    "upsert_frame",
    "upsert_frames_batch",
    "get_frame_by_depth",
    "get_frames_by_depth_range",
    "count_frames",
    "delete_frame",
    "get_depth_range",
]
