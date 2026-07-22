"""
app/db.py — SQLAlchemy engine and session factory.
Uses psycopg2 driver; connection string from Settings.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,   # detect stale connections before checkout
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


def get_db():
    """FastAPI dependency: yield a DB session and close on teardown."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
