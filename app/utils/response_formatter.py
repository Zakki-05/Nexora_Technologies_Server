import json
from fastapi import Request

EXCLUDED_PATHS = {"/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect", "/auth/token"}

RESOURCE_LABELS = {
    "auth": "Authentication",
    "employees": "Employees",
    "departments": "Departments",
    "attendance": "Attendance records",
    "breaks": "Break sessions",
    "leaves": "Leave requests",
    "leave-types": "Leave types",
    "dashboard": "Dashboard metrics",
    "holidays": "Holidays",
    "salaries": "Salary records",
    "notifications": "Notifications",
    "announcements": "Announcements",
    "audit-logs": "Audit logs",
    "documents": "Documents",
    "reports": "Reports",
    "expenses": "Expense claims",
    "organizations": "Organizations",
    "health": "System health status",
}

def build_success_message(method: str, path: str, payload: object) -> str:
    if isinstance(payload, dict) and isinstance(payload.get("message"), str) and payload["message"].strip():
        return payload["message"].strip()

    clean_path = path.strip("/")
    if not clean_path:
        return "API status retrieved successfully"

    parts = clean_path.split("/")
    resource = RESOURCE_LABELS.get(parts[0], parts[0].replace("-", " ").capitalize())

    if parts[0] == "auth":
        if "login" in parts:
            return "Login successful"
        if "register" in parts:
            return "User registered successfully"
        if "refresh" in parts:
            return "Token refreshed successfully"
        if "me" in parts:
            return "Profile retrieved successfully"
        if "users" in parts and method == "GET":
            return "Users retrieved successfully"

    action_map = {
        "GET": "retrieved successfully",
        "POST": "created successfully",
        "PUT": "updated successfully",
        "PATCH": "updated successfully",
        "DELETE": "deleted successfully",
    }
    action = action_map.get(method.upper(), "processed successfully")
    return f"{resource} {action}"

def wrap_error_payload(status_code: int, message: str, data: object = None) -> dict:
    return {
        "success": False,
        "message": message,
        "status_code": status_code,
        "data": data if data is not None else {},
    }

def wrap_success_payload(status_code: int, message: str, data: object) -> dict:
    return {
        "success": True,
        "message": message,
        "status_code": status_code,
        "data": data if data is not None else {},
    }

def should_wrap_response(request: Request, content_type: str) -> bool:
    path = request.url.path.rstrip("/") or "/"
    if path in EXCLUDED_PATHS:
        return False
    if path.startswith("/uploads"):
        return False
    if "application/json" not in (content_type or "").lower():
        return False
    return True

def try_parse_json(body_bytes: bytes):
    try:
        return json.loads(body_bytes.decode("utf-8"))
    except Exception:
        return None
