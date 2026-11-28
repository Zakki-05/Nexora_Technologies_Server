from typing import Any
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.leave import Leave
from app.models.leave_balance import LeaveBalance
from app.models.user import User


def get_my_leave_balance(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    """Return the authenticated employee's current leave balances."""
    emp = db.query(Employee).filter(
        Employee.user_id == user.id,
        Employee.organization_id == user.organization_id,
    ).first()
    if not emp:
        return {"error": "No employee profile linked to this user."}

    bal = db.query(LeaveBalance).filter(LeaveBalance.employee_id == emp.id).first()
    if not bal:
        return {"employee_code": emp.employee_code, "message": "Leave balance not initialized."}

    return {
        "employee_code": emp.employee_code,
        "year": bal.year,
        "annual": {
            "total": bal.annual_total,
            "used": bal.annual_used,
            "remaining": max(0, bal.annual_total - bal.annual_used),
        },
        "sick": {
            "total": bal.sick_total,
            "used": bal.sick_used,
            "remaining": max(0, bal.sick_total - bal.sick_used),
        },
        "casual": {
            "total": bal.casual_total,
            "used": bal.casual_used,
            "remaining": max(0, bal.casual_total - bal.casual_used),
        },
        "unpaid_used": bal.unpaid_used,
        "pending_reserved": bal.pending_reserved,
        "carried_forward": bal.carried_forward,
    }


def get_my_leave_requests(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    """Return recent leave requests for the authenticated employee."""
    emp = db.query(Employee).filter(
        Employee.user_id == user.id,
        Employee.organization_id == user.organization_id,
    ).first()
    if not emp:
        return {"error": "No employee profile linked to this user."}

    rows = (
        db.query(Leave)
        .filter(Leave.employee_id == emp.id)
        .order_by(Leave.created_at.desc())
        .limit(10)
        .all()
    )
    return {
        "employee_code": emp.employee_code,
        "requests": [
            {
                "id": lv.id,
                "leave_type": lv.leave_type,
                "start_date": lv.start_date.isoformat(),
                "end_date": lv.end_date.isoformat(),
                "days_count": float(lv.days_count),
                "status": lv.status,
                "is_half_day": lv.is_half_day,
            }
            for lv in rows
        ],
    }


def get_pending_leave_requests(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    """Return pending leave requests across the organization (HR/Admin only)."""
    limit = min(max(int(args.get("limit", 15)), 1), 30)
    rows = (
        db.query(Leave, Employee.employee_code, Employee.full_name)
        .join(Employee, Employee.id == Leave.employee_id)
        .filter(
            Employee.organization_id == user.organization_id,
            Leave.status == "PENDING",
        )
        .order_by(Leave.created_at.asc())
        .limit(limit)
        .all()
    )
    return {
        "organization_id": user.organization_id,
        "pending_count": len(rows),
        "requests": [
            {
                "leave_id": lv.id,
                "employee_code": code,
                "employee_name": name,
                "leave_type": lv.leave_type,
                "start_date": lv.start_date.isoformat(),
                "end_date": lv.end_date.isoformat(),
                "days_count": float(lv.days_count),
            }
            for lv, code, name in rows
        ],
    }
