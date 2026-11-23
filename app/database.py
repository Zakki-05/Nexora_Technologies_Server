import os
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger(__name__)

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(base_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:root@localhost:5432/EMS")

# Normalize PostgreSQL dialect for SQLAlchemy 2.0+ compatibility (Render, Supabase, Neon)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

if os.environ.get("VERCEL"):
    fallback_db_path = "/tmp/ems.db"
else:
    fallback_db_path = os.path.join(base_dir, "ems.db").replace("\\", "/")
fallback_url = f"sqlite:///{fallback_db_path}"

# Configure engine depending on dialect and test connectivity
if DATABASE_URL.startswith("sqlite"):
    if "./" in DATABASE_URL:
        DATABASE_URL = fallback_url
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
    print(f"[EMS DB] Using SQLite database: {DATABASE_URL}")
else:
    is_local = "localhost" in DATABASE_URL or "127.0.0.1" in DATABASE_URL
    postgres_available = False

    if is_local:
        # Fast socket pre-check to prevent 20s OS network timeouts if local Postgres is stopped
        try:
            import socket
            from urllib.parse import urlparse
            parsed = urlparse(DATABASE_URL)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 5432
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex((host, port)) == 0:
                    postgres_available = True
        except Exception:
            postgres_available = False
    else:
        # Remote production database (Neon, Supabase, Render PostgreSQL, etc.)
        postgres_available = True

    if postgres_available:
        try:
            connect_args = {"connect_timeout": 5}
            candidate_engine = create_engine(
                DATABASE_URL,
                connect_args=connect_args,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10
            )
            with candidate_engine.connect() as conn:
                pass
            engine = candidate_engine
            logger.info("Connected successfully to PostgreSQL database.")
            print(f"[EMS DB] Connected successfully to PostgreSQL database ({DATABASE_URL.split('@')[-1]}).")
        except Exception as e:
            logger.warning(
                f"Could not connect to PostgreSQL ({e}). "
                f"Automatically falling back to local SQLite: {fallback_url}"
            )
            print(f"[EMS DB] PostgreSQL unreachable ({e}). Falling back to local SQLite: {fallback_url}")
            engine = create_engine(
                fallback_url,
                connect_args={"check_same_thread": False}
            )
    else:
        logger.info(f"[EMS DB] Local PostgreSQL service unreachable. Falling back to SQLite: {fallback_url}")
        print(f"[EMS DB] PostgreSQL unreachable. Falling back to local SQLite: {fallback_url}")
        engine = create_engine(
            fallback_url,
            connect_args={"check_same_thread": False}
        )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def init_db():
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        if "users" not in existing_tables:
            print("[EMS DB] Database tables not found. Initializing schema...")
            Base.metadata.create_all(bind=engine)
            try:
                from scripts.seed import seed_database
                seed_database()
            except Exception as se:
                print(f"[EMS DB] Seed notice: {se}")
        else:
            print(f"[EMS DB] Schema verified. {len(existing_tables)} tables present.")
    except Exception as e:
        print(f"[EMS DB] Database initialization notice: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

