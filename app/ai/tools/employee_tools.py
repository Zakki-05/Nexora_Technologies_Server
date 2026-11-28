from datetime import date
from typing import Any
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.holiday import Holiday
from app.models.user import User


def get_my_profile(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    """Return the authenticated employee's own non-sensitive profile summary."""
    emp = db.query(Employee).filter(
        Employee.user_id == user.id,
        Employee.organization_id == user.organization_id,
    ).first()
    if not emp:
        return {
            "has_employee_record": False,
            "username": user.username,
            "role": user.role,
            "organization_id": user.organization_id,
        }
    return {
        "has_employee_record": True,
        "employee_code": emp.employee_code,
        "full_name": emp.full_name,
        "position": emp.position,
        "department_id": emp.department_id,
        "department_name": emp.department.name if emp.department else None,
        "employment_status": emp.employment_status,
        "hire_date": emp.hire_date.isoformat(),
    }


def get_upcoming_holidays(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    """Return upcoming company holidays from today onward."""
    limit = min(max(int(args.get("limit", 10)), 1), 25)
    today = date.today()
    rows = (
        db.query(Holiday)
        .filter(Holiday.date >= today)
        .order_by(Holiday.date.asc())
        .limit(limit)
        .all()
    )
    return {
        "as_of": today.isoformat(),
        "holidays": [
            {
                "name": h.name,
                "date": h.date.isoformat(),
                "is_optional": h.is_optional,
                "description": h.description,
            }
            for h in rows
        ],
    }


def get_workforce_headcount(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    """Return organization-scoped headcount breakdown by employment status (HR/Admin only)."""
    rows = (
        db.query(Employee.employment_status, func.count(Employee.id))
        .filter(Employee.organization_id == user.organization_id)
        .group_by(Employee.employment_status)
        .all()
    )
    by_status = {status or "UNKNOWN": int(cnt) for status, cnt in rows}
    return {
        "organization_id": user.organization_id,
        "total_employees": sum(by_status.values()),
        "by_status": by_status,
    }
