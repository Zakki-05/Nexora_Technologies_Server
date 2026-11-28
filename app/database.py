import os
import re
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool
from sqlalchemy.exc import OperationalError, SQLAlchemyError

logger = logging.getLogger("ems.database")

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(base_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Default for local development with PostgreSQL 19
    DATABASE_URL = "postgresql+psycopg2://postgres:root@localhost:5433/employees"

# Normalize PostgreSQL dialect for SQLAlchemy 2.0+ compatibility
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

def mask_connection_string(url: str) -> str:
    """Mask password in connection string for safe diagnostic logging."""
    if not url:
        return ""
    return re.sub(r':([^:@]+)@', ':***@', url)

IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

# Connection arguments with fast connect timeout to prevent serverless execution hangs
connect_args = {
    "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "10"))
}

# Configure engine with serverless-appropriate pooling
if IS_SERVERLESS:
    # On serverless (Vercel Lambda), NullPool prevents connection leakage and pool exhaustion
    engine = create_engine(
        DATABASE_URL,
        poolclass=NullPool,
        connect_args=connect_args,
        echo=False
    )
    logger.info(f"Initialized PostgreSQL engine with NullPool for serverless ({mask_connection_string(DATABASE_URL)})")
else:
    # On persistent servers or local development, QueuePool maintains warm connections with pre-ping
    engine = create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args=connect_args,
        echo=False
    )
    logger.info(f"Initialized PostgreSQL engine with QueuePool ({mask_connection_string(DATABASE_URL)})")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def check_db_connection() -> tuple[bool, str]:
    """Validate database connectivity with a fast SELECT 1 query."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
        return True, "PostgreSQL connection active"
    except Exception as e:
        safe_msg = str(e).split("\n")[0]
        # Never leak password in error string
        safe_msg = re.sub(r':([^:@]+)@', ':***@', safe_msg)
        logger.error(f"Database connection check failed: {safe_msg}")
        return False, safe_msg

def init_db():
    """Verify database connectivity and schema on startup without destructive operations."""
    try:
        is_ok, msg = check_db_connection()
        if not is_ok:
            logger.error(f"[EMS DB] CRITICAL: Cannot connect to PostgreSQL: {msg}")
            print(f"[EMS DB] CRITICAL: Cannot connect to PostgreSQL at {mask_connection_string(DATABASE_URL)}. Details: {msg}")
            return

        import app.models  # noqa: F401 - ensure all ORM models are registered
        Base.metadata.create_all(bind=engine)

        # Safely add organization_id on pre-existing tables if missing
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, slug, company_code, timezone, is_active, subscription_plan) "
                    "VALUES (1, 'Nexora Technologies Inc.', 'nexora', 'NEX-001', 'Asia/Kolkata', true, 'ENTERPRISE') "
                    "ON CONFLICT (id) DO NOTHING"
                )
            )
            for tbl in ("users", "employees", "departments"):
                conn.execute(
                    text(
                        f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS organization_id INTEGER NOT NULL DEFAULT 1"
                    )
                )

        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        logger.info(f"[EMS DB] Verified PostgreSQL schema. {len(existing_tables)} tables present.")
        print(f"[EMS DB] Verified PostgreSQL schema. {len(existing_tables)} tables present.")
    except Exception as e:
        safe_err = re.sub(r':([^:@]+)@', ':***@', str(e))
        logger.error(f"[EMS DB] Startup initialization notice: {safe_err}")
        print(f"[EMS DB] Startup initialization notice: {safe_err}")

def get_db():
    """Dependency that yields an active database session and ensures it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
