"""Database engine and session helpers for the local SQLite persistence layer."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_DEFAULT_DB_FILENAME = "resume_agent.db"
_DATABASE_URL_ENV = "RESUME_AGENT_DB_URL"

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_current_database_url: str | None = None


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base for all local persistence tables."""
    pass


def get_database_url() -> str:
    """Return the active database URL, defaulting to the local SQLite file."""
    database_url = os.getenv(_DATABASE_URL_ENV)
    if database_url:
        return database_url

    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    database_path = data_dir / _DEFAULT_DB_FILENAME
    return f"sqlite:///{database_path.as_posix()}"


def get_engine() -> Engine:
    """Return a cached SQLAlchemy engine for the currently configured database URL."""
    global _engine, _session_factory, _current_database_url

    database_url = get_database_url()
    if _engine is not None and _current_database_url == database_url:
        return _engine

    if _engine is not None:
        _engine.dispose()

    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    _engine = create_engine(database_url, connect_args=connect_args)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    _current_database_url = database_url
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return a cached session factory bound to the active engine."""
    global _session_factory

    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a database session and handle commit, rollback and close automatically."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all configured database tables for the active database URL."""
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def reset_database_state() -> None:
    """Dispose cached database resources so the next startup recreates fresh state."""
    global _engine, _session_factory, _current_database_url

    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _current_database_url = None
