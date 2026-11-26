from datetime import date
from typing import Annotated, Optional
from decimal import Decimal
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.database import get_db
from app.models.user import User
from app.models.employee import Employee
from app.models.department import Department
from app.models.leave import Leave
from app.models.attendance import Attendance
from app.models.salary import Salary
from app.models.holiday import Holiday
from app.models.notification import Notification
from app.models.announcement import Announcement
from app.services.attendance_service import get_today_attendance
from app.services.leave_service import get_employee_balance
from app.services.holiday_service import get_upcoming_holidays
from app.services.announcement_service import get_announcements_for_user
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import get_current_admin

router = APIRouter()

@router.get("/admin")
@router.get("/")
def get_admin_dashboard(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    today = date.today()

    total_employees = db.query(Employee).count()
    active_employees = db.query(Employee).filter(Employee.employment_status == "ACTIVE").count()
    total_departments = db.query(Department).count()

    total_leaves = db.query(Leave).count()
    pending_leaves = db.query(Leave).filter(Leave.status == "PENDING").count()

    # Today's attendance
    today_records = db.query(Attendance).filter(Attendance.date == today).all()
    today_present = sum(1 for a in today_records if a.status in {"PRESENT", "LATE"})
    today_late = sum(1 for a in today_records if a.is_late or a.status == "LATE")
    attendance_rate = round((today_present / active_employees * 100), 1) if active_employees > 0 else 0.0

    # Total payroll
    payroll_sum = db.query(func.sum(Employee.salary)).filter(
        Employee.employment_status == "ACTIVE"
    ).scalar() or Decimal("0.00")

    # Department distribution for charts - single optimized query eliminating N+1 loop
    dept_distribution_raw = (
        db.query(Department.id, Department.name, func.count(Employee.id).label("count"))
        .outerjoin(Employee, Employee.department_id == Department.id)
        .group_by(Department.id, Department.name)
        .order_by(func.count(Employee.id).desc())
        .all()
    )
    dept_distribution = [
        {"department_id": d_id, "name": d_name, "count": count}
        for d_id, d_name, count in dept_distribution_raw
    ]

    # Recent leaves with eager employee loading
    recent_leaves_query = (
        db.query(Leave)
        .options(joinedload(Leave.employee))
        .order_by(Leave.id.desc())
        .limit(5)
        .all()
    )
    recent_leaves = []
    for lv in recent_leaves_query:
        emp_name = lv.employee.full_name if lv.employee else "Unknown"
        recent_leaves.append({
            "id": lv.id,
            "employee_name": emp_name,
            "leave_type": lv.leave_type,
            "days_count": lv.days_count,
            "status": lv.status,
            "start_date": str(lv.start_date)
        })

    # Recent announcements
    recent_announcements = db.query(Announcement).filter(
        Announcement.is_active == True
    ).order_by(Announcement.created_at.desc()).limit(5).all()

    return {
        "total_employees": total_employees,
        "active_employees": active_employees,
        "total_departments": total_departments,
        "total_leaves": total_leaves,
        "pending_leaves": pending_leaves,
        "today_present": today_present,
        "today_late": today_late,
        "attendance_rate": attendance_rate,
        "monthly_payroll": float(payroll_sum),
        "department_distribution": dept_distribution,
        "recent_leaves": recent_leaves,
        "recent_announcements": [
            {
                "id": a.id,
                "title": a.title,
                "priority": a.priority,
                "target_type": a.target_type,
                "created_at": str(a.created_at)
            }
            for a in recent_announcements
        ]
    }

@router.get("/employee")
def get_employee_dashboard(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    from app.services.employee_service import ensure_employee_profile
    emp = ensure_employee_profile(current_user, db)
    today_record = get_today_attendance(emp.id, db)
    leave_balances = get_employee_balance(emp.id, db)
    upcoming = get_upcoming_holidays(db, limit=3)
    unread_notifs = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).count()
    my_pending_leaves = db.query(Leave).filter(
        Leave.employee_id == emp.id,
        Leave.status == "PENDING"
    ).count()

    today_info = None
    if today_record:
        today_info = {
            "check_in": str(today_record.check_in) if today_record.check_in else None,
            "check_out": str(today_record.check_out) if today_record.check_out else None,
            "work_hours": float(today_record.work_hours),
            "status": today_record.status,
            "is_late": today_record.is_late
        }

    # Fetch announcements accessible to this employee
    announcements_res = get_announcements_for_user(current_user, db, page=1, size=5, active_only=True)

    return {
        "employee": {
            "id": emp.id,
            "employee_code": emp.employee_code,
            "full_name": emp.full_name,
            "position": emp.position,
            "department": {"name": emp.department.name} if emp.department else {"name": "Assigned Department"}
        },
        "employee_id": emp.id,
        "employee_code": emp.employee_code,
        "full_name": emp.full_name,
        "position": emp.position,
        "department": emp.department.name if emp.department else "N/A",
        "today_attendance": today_info,
        "leave_balance": {
            "annual_remaining": leave_balances.annual_remaining,
            "sick_remaining": leave_balances.sick_remaining,
            "casual_remaining": leave_balances.casual_remaining
        },
        "leave_balances": [
            {
                "id": tb.leave_type_id,
                "leave_type": tb.leave_type_name,
                "code": tb.leave_type_code,
                "total_days": tb.annual_allocation,
                "used_days": tb.approved_consumed,
                "pending_days": tb.pending_reserved,
                "remaining_days": tb.available,
                "is_paid": tb.is_paid
            }
            for tb in leave_balances.type_balances
        ],
        "pending_leaves_count": my_pending_leaves,
        "unread_notifications": unread_notifs,
        "upcoming_holidays": [
            {"id": h.id, "name": h.name, "date": str(h.date), "is_optional": h.is_optional}
            for h in upcoming
        ],
        "recent_announcements": [
            {
                "id": a.id,
                "title": a.title,
                "message": a.message,
                "priority": a.priority,
                "created_at": str(a.created_at)
            }
            for a in announcements_res.items
        ]
    }
