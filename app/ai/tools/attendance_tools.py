from datetime import date, timedelta
from typing import Any
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.user import User


def get_my_attendance_summary(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    """Return the authenticated employee's own attendance summary over recent days."""
    days = min(max(int(args.get("days", 14)), 1), 90)
    emp = db.query(Employee).filter(
        Employee.user_id == user.id,
        Employee.organization_id == user.organization_id,
    ).first()
    if not emp:
        return {"error": "No employee profile linked to this user."}

    since = date.today() - timedelta(days=days)
    records = (
        db.query(Attendance)
        .filter(Attendance.employee_id == emp.id, Attendance.date >= since)
        .order_by(Attendance.date.desc())
        .limit(30)
        .all()
    )
    total_hours = sum(float(r.work_hours or 0) for r in records)
    late_days = sum(1 for r in records if r.is_late)
    return {
        "employee_code": emp.employee_code,
        "period_days": days,
        "records_count": len(records),
        "total_work_hours": round(total_hours, 2),
        "late_days": late_days,
        "recent_records": [
            {
                "date": r.date.isoformat(),
                "status": r.status,
                "check_in": r.check_in.isoformat() if r.check_in else None,
                "check_out": r.check_out.isoformat() if r.check_out else None,
                "work_hours": float(r.work_hours or 0),
                "is_late": r.is_late,
            }
            for r in records[:10]
        ],
    }


def get_organization_attendance_summary(
    db: Session, user: User, args: dict[str, Any]
) -> dict[str, Any]:
    """Return organization-wide attendance counts for a given date (HR/Admin only)."""
    target_date_str = args.get("date")
    try:
        target_date = date.fromisoformat(target_date_str) if target_date_str else date.today()
    except ValueError:
        target_date = date.today()

    rows = (
        db.query(Attendance.status, func.count(Attendance.id))
        .join(Employee, Employee.id == Attendance.employee_id)
        .filter(
            Employee.organization_id == user.organization_id,
            Attendance.date == target_date,
        )
        .group_by(Attendance.status)
        .all()
    )
    by_status = {status: int(cnt) for status, cnt in rows}
    return {
        "organization_id": user.organization_id,
        "date": target_date.isoformat(),
        "total_marked": sum(by_status.values()),
        "by_status": by_status,
    }
