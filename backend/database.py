"""
Database connection setup. SQLite for the hackathon build — swap the URL
for Postgres later without touching any other file, since everything
goes through SQLAlchemy's session/engine abstraction.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./attendance.db"

# check_same_thread=False is needed for SQLite + FastAPI's threaded request handling.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a session, always closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Call once on startup (see main.py)."""
    # Import models here so they're registered on Base before create_all runs.
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
