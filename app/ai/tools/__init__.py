from dataclasses import dataclass
from typing import Any, Callable
from sqlalchemy.orm import Session

from app.ai.permissions import get_ai_role_tier
from app.ai.providers.base import AIToolDefinition
from app.ai.tools.attendance_tools import (
    get_my_attendance_summary,
    get_organization_attendance_summary,
)
from app.ai.tools.department_tools import list_departments_summary
from app.ai.tools.employee_tools import (
    get_my_profile,
    get_upcoming_holidays,
    get_workforce_headcount,
)
from app.ai.tools.leave_tools import (
    get_my_leave_balance,
    get_my_leave_requests,
    get_pending_leave_requests,
)
from app.ai.tools.payroll_tools import get_my_latest_salary, get_payroll_summary
from app.ai.tools.report_tools import get_system_audit_summary
from app.models.user import User

ALL_TIERS = {"employee", "hr", "finance", "auditor", "admin", "super_admin"}
HR_ADMIN_TIERS = {"hr", "admin", "super_admin"}
FINANCE_ADMIN_TIERS = {"finance", "admin", "super_admin"}
AUDIT_ADMIN_TIERS = {"auditor", "admin", "super_admin"}


@dataclass(frozen=True)
class RegisteredTool:
    definition: AIToolDefinition
    handler: Callable[[Session, User, dict[str, Any]], dict[str, Any]]
    allowed_tiers: set[str]


TOOL_REGISTRY: dict[str, RegisteredTool] = {
    "get_my_profile": RegisteredTool(
        definition=AIToolDefinition(
            name="get_my_profile",
            description="Get the current authenticated user's employee profile, position, and department.",
            parameters={"type": "object", "properties": {}},
        ),
        handler=get_my_profile,
        allowed_tiers=ALL_TIERS,
    ),
    "get_upcoming_holidays": RegisteredTool(
        definition=AIToolDefinition(
            name="get_upcoming_holidays",
            description="List upcoming company holidays.",
            parameters={
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "Max holidays to return (1-25)."}},
            },
        ),
        handler=get_upcoming_holidays,
        allowed_tiers=ALL_TIERS,
    ),
    "get_my_attendance_summary": RegisteredTool(
        definition=AIToolDefinition(
            name="get_my_attendance_summary",
            description="Get the current user's recent attendance history, hours worked, and late count.",
            parameters={
                "type": "object",
                "properties": {"days": {"type": "integer", "description": "Lookback days (1-90)."}},
            },
        ),
        handler=get_my_attendance_summary,
        allowed_tiers=ALL_TIERS,
    ),
    "get_my_leave_balance": RegisteredTool(
        definition=AIToolDefinition(
            name="get_my_leave_balance",
            description="Get the current user's annual, sick, casual, and pending reserved leave balances.",
            parameters={"type": "object", "properties": {}},
        ),
        handler=get_my_leave_balance,
        allowed_tiers=ALL_TIERS,
    ),
    "get_my_leave_requests": RegisteredTool(
        definition=AIToolDefinition(
            name="get_my_leave_requests",
            description="List the current user's recent leave requests and approval statuses.",
            parameters={"type": "object", "properties": {}},
        ),
        handler=get_my_leave_requests,
        allowed_tiers=ALL_TIERS,
    ),
    "get_my_latest_salary": RegisteredTool(
        definition=AIToolDefinition(
            name="get_my_latest_salary",
            description="Get the current user's latest salary slip summary.",
            parameters={"type": "object", "properties": {}},
        ),
        handler=get_my_latest_salary,
        allowed_tiers=ALL_TIERS,
    ),
    "list_departments_summary": RegisteredTool(
        definition=AIToolDefinition(
            name="list_departments_summary",
            description="List departments in the current organization and their employee counts.",
            parameters={"type": "object", "properties": {}},
        ),
        handler=list_departments_summary,
        allowed_tiers=ALL_TIERS,
    ),
    "get_workforce_headcount": RegisteredTool(
        definition=AIToolDefinition(
            name="get_workforce_headcount",
            description="Get total employee headcount and breakdown by employment status (HR/Admin only).",
            parameters={"type": "object", "properties": {}},
        ),
        handler=get_workforce_headcount,
        allowed_tiers=HR_ADMIN_TIERS,
    ),
    "get_organization_attendance_summary": RegisteredTool(
        definition=AIToolDefinition(
            name="get_organization_attendance_summary",
            description="Get organization-wide attendance breakdown for a date (HR/Admin only).",
            parameters={
                "type": "object",
                "properties": {"date": {"type": "string", "description": "ISO date YYYY-MM-DD (defaults to today)."}},
            },
        ),
        handler=get_organization_attendance_summary,
        allowed_tiers=HR_ADMIN_TIERS,
    ),
    "get_pending_leave_requests": RegisteredTool(
        definition=AIToolDefinition(
            name="get_pending_leave_requests",
            description="List pending leave requests awaiting approval (HR/Admin only).",
            parameters={
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "Max pending requests (1-30)."}},
            },
        ),
        handler=get_pending_leave_requests,
        allowed_tiers=HR_ADMIN_TIERS,
    ),
    "get_payroll_summary": RegisteredTool(
        definition=AIToolDefinition(
            name="get_payroll_summary",
            description="Get aggregated organization payroll totals (Finance/Admin only).",
            parameters={
                "type": "object",
                "properties": {
                    "month": {"type": "integer", "description": "Month (1-12)."},
                    "year": {"type": "integer", "description": "Four-digit year."},
                },
            },
        ),
        handler=get_payroll_summary,
        allowed_tiers=FINANCE_ADMIN_TIERS,
    ),
    "get_system_audit_summary": RegisteredTool(
        definition=AIToolDefinition(
            name="get_system_audit_summary",
            description="Get recent EMS and AI audit event counts and token usage (Super Admin/Auditor only).",
            parameters={
                "type": "object",
                "properties": {"days": {"type": "integer", "description": "Lookback days (1-30)."}},
            },
        ),
        handler=get_system_audit_summary,
        allowed_tiers=AUDIT_ADMIN_TIERS,
    ),
}


def get_authorized_tools(user: User) -> list[AIToolDefinition]:
    """Return only tool definitions permitted for the current user's role tier."""
    tier = get_ai_role_tier(user)
    return [tool.definition for tool in TOOL_REGISTRY.values() if tier in tool.allowed_tiers]


def execute_authorized_tool(
    db: Session,
    user: User,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a registered tool after re-verifying RBAC permissions."""
    tool = TOOL_REGISTRY.get(tool_name)
    if not tool:
        return {"error": f"Unknown tool '{tool_name}'."}

    tier = get_ai_role_tier(user)
    if tier not in tool.allowed_tiers:
        return {"error": f"Access denied for tool '{tool_name}' under role '{user.role}'."}

    return tool.handler(db, user, arguments or {})
