"""
Compatibility module: re-exports database components from app.database
to maintain backward compatibility with existing code.
"""
from app.database import Base, engine, SessionLocal, get_db, DATABASE_URL

__all__ = ["Base", "engine", "SessionLocal", "get_db", "DATABASE_URL"]
