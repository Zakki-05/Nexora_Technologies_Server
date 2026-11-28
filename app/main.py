from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, OperationalError
import re
import logging
import os

from app.utils.response_formatter import (
    build_success_message,
    wrap_error_payload,
    wrap_success_payload,
    should_wrap_response,
    try_parse_json,
)

logger = logging.getLogger("ems.api")

from fastapi.staticfiles import StaticFiles

from app.routers import (
    ai,
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

class ResponseEnvelopeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = (scope.get("path") or "/").rstrip("/") or "/"
        method = scope.get("method", "GET")

        # Skip docs, OAuth2 token endpoint, static uploads, and SSE streams
        if path in {"/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect", "/auth/token", "/ai/chat/stream"} or path.startswith("/uploads"):
            async def send_with_headers(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.extend([
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"x-xss-protection", b"1; mode=block"),
                        (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    ])
                    message["headers"] = headers
                await send(message)

            await self.app(scope, receive, send_with_headers)
            return

        response_start = None
        body_chunks = []

        async def capture_send(message):
            nonlocal response_start
            if message["type"] == "http.response.start":
                response_start = message
            elif message["type"] == "http.response.body":
                body_chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    raw_headers = list(response_start.get("headers", []))
                    headers_dict = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in raw_headers}
                    content_type = headers_dict.get("content-type", "")
                    status_code = response_start["status"]
                    full_body = b"".join(body_chunks)

                    if "application/json" in content_type.lower():
                        parsed = try_parse_json(full_body)
                        if parsed is not None:
                            if isinstance(parsed, dict) and {"success", "message", "status_code", "data"}.issubset(parsed.keys()):
                                wrapped = parsed
                            elif status_code >= 400:
                                err_msg = parsed.get("detail") if isinstance(parsed, dict) else "Request failed"
                                if isinstance(err_msg, list):
                                    err_msg = "; ".join(str(item) for item in err_msg)
                                wrapped = wrap_error_payload(status_code, str(err_msg or "Request failed"))
                            else:
                                msg = build_success_message(method, path, parsed)
                                wrapped = wrap_success_payload(status_code, msg, parsed)

                            import json as _json
                            full_body = _json.dumps(wrapped).encode("utf-8")
                            raw_headers = [(k, v) for k, v in raw_headers if k.lower() != b"content-length"]
                            raw_headers.append((b"content-length", str(len(full_body)).encode("latin-1")))

                    raw_headers.extend([
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"x-xss-protection", b"1; mode=block"),
                        (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    ])
                    response_start["headers"] = raw_headers
                    await send(response_start)
                    await send({"type": "http.response.body", "body": full_body, "more_body": False})

        await self.app(scope, receive, capture_send)

app.add_middleware(ResponseEnvelopeMiddleware)

# Centralized Error Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=wrap_error_payload(exc.status_code, detail),
        headers=exc.headers,
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        field = " -> ".join(str(loc) for loc in err.get("loc", []))
        errors.append(f"{field}: {err.get('msg')}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=wrap_error_payload(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Validation error: " + "; ".join(errors),
            {"errors": exc.errors()},
        ),
    )

@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=wrap_error_payload(
            status.HTTP_409_CONFLICT,
            "Database conflict or constraint violation. Ensure unique fields are not duplicated.",
        ),
    )

@app.exception_handler(OperationalError)
async def operational_exception_handler(request: Request, exc: OperationalError):
    safe_err = re.sub(r':([^:@]+)@', ':***@', str(exc)).split("\n")[0]
    logger.error(f"[EMS DB Connection Error] {request.method} {request.url.path}: {safe_err}")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=wrap_error_payload(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Database service is temporarily unreachable. Please verify PostgreSQL connection and network settings.",
        ),
    )

@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    safe_err = re.sub(r':([^:@]+)@', ':***@', str(exc)).split("\n")[0]
    logger.error(f"[EMS DB Error] {request.method} {request.url.path}: {safe_err}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=wrap_error_payload(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "A database error occurred. Please verify PostgreSQL data constraints.",
        ),
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
app.include_router(ai.router, prefix="/ai", tags=["Nexora AI"])

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
