"""Database connection management for the Awren Cognitive OS."""

from typing import Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from awren_core.settings import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None


def get_engine() -> Engine:
    """Get or create the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_local() -> sessionmaker[Session]:
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _SessionLocal


def create_session() -> Session:
    """Create a new database session."""
    return get_session_local()()


def init_db() -> None:
    """Create all tables. Useful for tests and first-time setup."""
    Base.metadata.create_all(bind=get_engine())
