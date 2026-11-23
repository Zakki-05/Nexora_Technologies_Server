from datetime import datetime, date
from typing import Optional, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

def to_naive_datetime(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt

def safe_diff_seconds(dt1: Optional[datetime], dt2: Optional[datetime]) -> float:
    if not dt1 or not dt2:
        return 0.0
    n1 = to_naive_datetime(dt1)
    n2 = to_naive_datetime(dt2)
    return (n1 - n2).total_seconds()

from app.models.break_session import BreakSession
from app.models.attendance import Attendance
from app.models.attendance_session import AttendanceSession
from app.models.attendance_policy import AttendancePolicy
from app.schemas.break_session import BreakStatusResponse

def get_policy(db: Session) -> AttendancePolicy:
    policy = db.query(AttendancePolicy).filter(AttendancePolicy.is_active == True).first()
    if not policy:
        # Fallback default
        from datetime import time
        policy = AttendancePolicy(
            policy_name="Default Policy",
            office_start_time=time(9, 0),
            office_end_time=time(18, 0),
            grace_period_minutes=30,
            late_threshold_time=time(9, 30),
            full_day_minutes=480,
            half_day_minutes=240,
            max_daily_break_minutes=90,
            paid_break_types="TEA_BREAK,SHORT_BREAK",
            unpaid_break_types="LUNCH_BREAK,PERSONAL_BREAK,OTHER_BREAK"
        )
    return policy

def get_active_break_for_employee(employee_id: int, db: Session) -> Optional[BreakSession]:
    return db.query(BreakSession).filter(
        BreakSession.employee_id == employee_id,
        BreakSession.break_end.is_(None)
    ).order_by(BreakSession.id.desc()).first()

def start_break(employee_id: int, break_type: str, remarks: Optional[str], db: Session) -> BreakSession:
    today = date.today()
    attendance = db.query(Attendance).filter(
        Attendance.employee_id == employee_id,
        Attendance.date == today
    ).first()

    if not attendance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot start a break without an active attendance record. Please punch in first."
        )

    # Validate an active working session exists
    active_session = db.query(AttendanceSession).filter(
        AttendanceSession.attendance_id == attendance.id,
        AttendanceSession.employee_id == employee_id,
        AttendanceSession.punch_out.is_(None)
    ).first()

    if not active_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot start a break because you are not currently punched in. Please punch in to start work."
        )

    # Check if already on break
    active_break = get_active_break_for_employee(employee_id, db)
    if active_break:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You already have an active {active_break.break_type.replace('_', ' ').title()} in progress. Please end it before starting another."
        )

    policy = get_policy(db)
    paid_types = [p.strip().upper() for p in policy.paid_break_types.split(",")]
    is_paid = break_type.strip().upper() in paid_types

    break_obj = BreakSession(
        attendance_id=attendance.id,
        session_id=active_session.id,
        employee_id=employee_id,
        break_type=break_type.strip().upper(),
        break_start=datetime.now(),
        break_end=None,
        duration_minutes=0,
        is_paid=is_paid,
        remarks=remarks
    )
    db.add(break_obj)
    db.commit()
    db.refresh(break_obj)
    return break_obj

def end_break(employee_id: int, db: Session) -> BreakSession:
    active_break = get_active_break_for_employee(employee_id, db)
    if not active_break:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active break in progress to end."
        )

    now = datetime.now()
    active_break.break_end = now
    duration = int(round(safe_diff_seconds(now, active_break.break_start) / 60))
    active_break.duration_minutes = max(1, duration)

    # Recalculate attendance master totals
    attendance = db.query(Attendance).filter(Attendance.id == active_break.attendance_id).first()
    if attendance:
        breaks = db.query(BreakSession).filter(
            BreakSession.attendance_id == attendance.id,
            BreakSession.break_end.is_not(None)
        ).all()
        total_m = sum(b.duration_minutes for b in breaks) + active_break.duration_minutes
        paid_m = sum(b.duration_minutes for b in breaks if b.is_paid) + (active_break.duration_minutes if active_break.is_paid else 0)
        unpaid_m = total_m - paid_m
        attendance.total_break_minutes = total_m
        attendance.paid_break_minutes = paid_m
        attendance.unpaid_break_minutes = unpaid_m

    db.commit()
    db.refresh(active_break)
    return active_break

def get_break_status(employee_id: int, db: Session) -> BreakStatusResponse:
    today = date.today()
    active_break = get_active_break_for_employee(employee_id, db)

    attendance = db.query(Attendance).filter(
        Attendance.employee_id == employee_id,
        Attendance.date == today
    ).first()

    total_break = attendance.total_break_minutes if attendance else 0
    paid_break = attendance.paid_break_minutes if attendance else 0
    unpaid_break = attendance.unpaid_break_minutes if attendance else 0

    breaks_count = 0
    if attendance:
        breaks_count = db.query(BreakSession).filter(BreakSession.attendance_id == attendance.id).count()

    return BreakStatusResponse(
        is_on_break=active_break is not None,
        current_break=active_break,
        total_break_minutes=total_break,
        paid_break_minutes=paid_break,
        unpaid_break_minutes=unpaid_break,
        breaks_taken_count=breaks_count
    )

def get_employee_breaks_for_date(employee_id: int, target_date: date, db: Session) -> List[BreakSession]:
    attendance = db.query(Attendance).filter(
        Attendance.employee_id == employee_id,
        Attendance.date == target_date
    ).first()

    if not attendance:
        return []

    return db.query(BreakSession).filter(
        BreakSession.attendance_id == attendance.id
    ).order_by(BreakSession.break_start.asc()).all()
