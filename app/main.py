from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, OperationalError
import re
import logging
import os

logger = logging.getLogger("ems.api")

from fastapi.staticfiles import StaticFiles

from app.routers import (
    auth,
    employees,
    departments,
    attendance,
    breaks,
    leaves,
    leave_types,
    dashboard,
    holidays,
    salaries,
    notifications,
    announcements,
    audit_logs,
    documents,
    reports,
    expenses,
    organizations
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database import init_db
    init_db()
    yield

app = FastAPI(
    title="Nexora Workforce API",
    description="Enterprise API for workforce management, employee records, payroll, leave tracking, documents, and attendance by Nexora Technologies.",
    version="2.0.0",
    lifespan=lifespan
)

# CORS Configuration - Explicit trusted origins + configurable ALLOWED_ORIGINS env var
default_origins = [
    "https://nexoratechnologieszakki.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "capacitor://localhost",
    "https://localhost",
]
extra_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
allowed_origins = list(dict.fromkeys(default_origins + extra_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https://nexora-technologies-ui.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Centralized Error Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        field = " -> ".join(str(loc) for loc in err.get("loc", []))
        errors.append(f"{field}: {err.get('msg')}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error: " + "; ".join(errors),
            "errors": exc.errors()
        }
    )

@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": "Database conflict or constraint violation. Ensure unique fields are not duplicated."
        }
    )

@app.exception_handler(OperationalError)
async def operational_exception_handler(request: Request, exc: OperationalError):
    safe_err = re.sub(r':([^:@]+)@', ':***@', str(exc)).split("\n")[0]
    logger.error(f"[EMS DB Connection Error] {request.method} {request.url.path}: {safe_err}")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": "Database service is temporarily unreachable. Please verify PostgreSQL connection and network settings."
        }
    )

@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    safe_err = re.sub(r':([^:@]+)@', ':***@', str(exc)).split("\n")[0]
    logger.error(f"[EMS DB Error] {request.method} {request.url.path}: {safe_err}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "A database error occurred. Please verify PostgreSQL data constraints."
        }
    )

# Ensure uploads folders exist & mount static uploads
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/tmp/uploads" if os.environ.get("VERCEL") else os.path.join(os.getcwd(), "uploads"))
try:
    os.makedirs(os.path.join(UPLOAD_DIR, "avatars"), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_DIR, "documents"), exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
except Exception as ue:
    print(f"[EMS Static] Upload directory warning: {ue}")

# Routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(employees.router, prefix="/employees", tags=["Employees"])
app.include_router(departments.router, prefix="/departments", tags=["Departments"])
app.include_router(attendance.router, prefix="/attendance", tags=["Attendance"])
app.include_router(breaks.router, prefix="/breaks", tags=["Break Management"])
app.include_router(leaves.router, prefix="/leaves", tags=["Leaves"])
app.include_router(leave_types.router, prefix="/leave-types", tags=["Leave Types"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(holidays.router, prefix="/holidays", tags=["Holidays"])
app.include_router(salaries.router, prefix="/salaries", tags=["Salaries"])
app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
app.include_router(announcements.router, prefix="/announcements", tags=["Announcements"])
app.include_router(audit_logs.router, prefix="/audit-logs", tags=["Audit Logs"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])
app.include_router(expenses.router, prefix="/expenses", tags=["Expenses"])
app.include_router(organizations.router, prefix="/organizations", tags=["Organizations"])

@app.get("/", tags=["Home"])
def home():
    return {
        "message": "Welcome to Employee Management System API",
        "status": "Running",
        "version": "1.0.0"
    }

@app.get("/health", tags=["Health"])
def health_check():
    from app.database import check_db_connection
    is_connected, info = check_db_connection()
    if not is_connected:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "degraded",
                "database": "disconnected",
                "engine": "PostgreSQL",
                "detail": info
            }
        )
    return {
        "status": "healthy",
        "database": "connected",
        "engine": "PostgreSQL"
    }
