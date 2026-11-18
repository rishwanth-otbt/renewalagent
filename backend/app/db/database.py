"""
Database connection.

The connection string comes from DATABASE_URL (environment or backend/.env). Default: the local
SQL Server LocalDB instance with Windows login, database `renewaldesk`.

Driver: mssql-python (Microsoft's driver). pyodbc is blocked by Windows Application Control on
this machine, and pure-TCP drivers such as pytds cannot reach LocalDB (named pipes only).

The engine is created on first use, so importing the app never needs a running database.
Tests call configure("sqlite://") to use an in-memory database instead.
"""
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DEFAULT_DATABASE_URL = (
    "mssql+mssqlpython://@(localdb)\\MSSQLLocalDB/renewaldesk?Trusted_Connection=yes&Encrypt=no"
)


class Base(DeclarativeBase):
    pass


_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def configure(url: Optional[str] = None) -> Engine:
    """(Re)create the engine. url defaults to DATABASE_URL, then the LocalDB default."""
    global _engine, _session_factory
    url = url or os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
    if _engine is not None:
        _engine.dispose()
    if url.startswith("sqlite"):
        # One shared in-memory connection, usable from the test client's worker thread.
        _engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        _engine = create_engine(url, pool_pre_ping=True)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        configure()
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """A session that commits on success and rolls back on error."""
    if _session_factory is None:
        configure()
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
