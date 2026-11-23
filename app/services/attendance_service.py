import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from fastapi import HTTPException, status

from app.models.attendance import Attendance
from app.models.attendance_session import AttendanceSession
from app.models.break_session import BreakSession
from app.models.attendance_policy import AttendancePolicy
from app.models.attendance_correction import AttendanceCorrection
from app.models.employee import Employee
from app.models.holiday import Holiday
from app.models.leave import Leave
from app.models.audit_log import AuditLog
from app.schemas.attendance import (
    AttendanceManualCreate,
    AttendanceUpdate,
    AttendanceResponse,
    AttendanceLiveStatusResponse,
    DailyAttendanceTimelineResponse,
    TimelineEvent,
    WeeklyAttendanceSummaryResponse,
    WeeklyDayItem,
    MonthlyAttendanceDetailedResponse,
    AttendanceSummary,
    DailyAttendanceReport,
    AttendanceCorrectionCreate,
    AttendanceCorrectionReview,
    AttendanceSessionResponse
)
from app.schemas.break_session import BreakSessionResponse
from app.schemas.common import PaginatedResponse
from app.utils.pagination import paginate

STANDARD_START_TIME = time(9, 30, 0)

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

def get_attendance_by_date(attendance_date: date, db: Session):
    return db.query(Attendance).filter(Attendance.date == attendance_date).all()

def format_minutes_to_hhmm(minutes: int) -> str:
    m = max(0, minutes)
    hours = m // 60
    mins = m % 60
    return f"{hours:02d}:{mins:02d}"

def get_policy(db: Session) -> AttendancePolicy:
    policy = db.query(AttendancePolicy).filter(AttendancePolicy.is_active == True).first()
    if not policy:
        policy = AttendancePolicy(
            policy_name="Standard Corporate Policy",
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

def calculate_work_hours(check_in: Optional[time], check_out: Optional[time]) -> Decimal:
    if not check_in or not check_out:
        return Decimal("0.00")
    dummy_date = date(2000, 1, 1)
    dt_in = datetime.combine(dummy_date, check_in)
    dt_out = datetime.combine(dummy_date, check_out)
    if dt_out < dt_in:
        dt_out += timedelta(days=1)
    seconds = safe_diff_seconds(dt_out, dt_in)
    return round(Decimal(seconds) / Decimal(3600), 2)

def check_in(employee_id: int, db: Session) -> Attendance:
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    today = date.today()
    now = datetime.now()
    current_time = now.time().replace(microsecond=0)
    policy = get_policy(db)

    attendance = db.query(Attendance).filter(
        Attendance.employee_id == employee_id,
        Attendance.date == today
    ).first()

    if attendance:
        # Check if already punched in
        active_session = db.query(AttendanceSession).filter(
            AttendanceSession.attendance_id == attendance.id,
            AttendanceSession.employee_id == employee_id,
            AttendanceSession.punch_out.is_(None)
        ).first()

        if active_session:
            # Idempotent: already punched in, return current attendance without error
            return attendance
    else:
        # First check-in of the day
        is_late = current_time > policy.late_threshold_time
        attendance = Attendance(
            employee_id=employee_id,
            date=today,
            check_in=current_time,
            check_out=None,
            work_hours=Decimal("0.00"),
            office_duration_minutes=0,
            actual_working_minutes=0,
            total_break_minutes=0,
            paid_break_minutes=0,
            unpaid_break_minutes=0,
            overtime_minutes=0,
            is_late=is_late,
            is_incomplete=True,
            status="PRESENT",
            remarks="Check-in via system"
        )
        db.add(attendance)
        db.commit()
        db.refresh(attendance)

    # Determine session number
    session_count = db.query(AttendanceSession).filter(
        AttendanceSession.attendance_id == attendance.id
    ).count()
    new_session_number = session_count + 1

    session = AttendanceSession(
        attendance_id=attendance.id,
        employee_id=employee_id,
        session_number=new_session_number,
        punch_in=now,
        punch_out=None,
        duration_minutes=0,
        status="ACTIVE"
    )
    db.add(session)
    attendance.check_out = None
    attendance.is_incomplete = True
    db.commit()
    db.refresh(attendance)
    return attendance

def check_out(employee_id: int, db: Session) -> Attendance:
    today = date.today()
    now = datetime.now()
    current_time = now.time().replace(microsecond=0)
    policy = get_policy(db)

    attendance = db.query(Attendance).filter(
        Attendance.employee_id == employee_id,
        Attendance.date == today
    ).first()

    if not attendance:
        # Auto-provision daily check-in and immediately close for seamless user experience
        attendance = Attendance(
            employee_id=employee_id,
            date=today,
            check_in=current_time,
            check_out=current_time,
            work_hours=Decimal("0.00"),
            office_duration_minutes=0,
            actual_working_minutes=0,
            total_break_minutes=0,
            paid_break_minutes=0,
            unpaid_break_minutes=0,
            overtime_minutes=0,
            is_late=False,
            is_incomplete=False,
            status="PRESENT",
            remarks="Recorded shift punch-out"
        )
        db.add(attendance)
        db.commit()
        db.refresh(attendance)
        return attendance

    active_session = db.query(AttendanceSession).filter(
        AttendanceSession.attendance_id == attendance.id,
        AttendanceSession.employee_id == employee_id,
        AttendanceSession.punch_out.is_(None)
    ).first()

    if not active_session:
        # Idempotent: already punched out today, return attendance cleanly
        return attendance

    # Auto-close any active break
    active_break = db.query(BreakSession).filter(
        BreakSession.attendance_id == attendance.id,
        BreakSession.employee_id == employee_id,
        BreakSession.break_end.is_(None)
    ).first()
    if active_break:
        active_break.break_end = now
        active_break.duration_minutes = max(1, int(round(safe_diff_seconds(now, active_break.break_start) / 60)))

    # Close active session
    active_session.punch_out = now
    session_dur = max(1, int(round(safe_diff_seconds(now, active_session.punch_in) / 60)))
    active_session.duration_minutes = session_dur
    active_session.status = "COMPLETED"

    # Update master attendance
    attendance.check_out = current_time

    # Calculate office duration (first punch in to this punch out)
    if attendance.check_in:
        dt_first = datetime.combine(today, attendance.check_in)
        dt_last = datetime.combine(today, current_time)
        if dt_last < dt_first:
            dt_last += timedelta(days=1)
        attendance.office_duration_minutes = int(round(safe_diff_seconds(dt_last, dt_first) / 60))

    # Calculate sum of all session durations
    completed_sessions = db.query(AttendanceSession).filter(
        AttendanceSession.attendance_id == attendance.id,
        AttendanceSession.punch_out.is_not(None)
    ).all()
    total_session_minutes = sum(s.duration_minutes for s in completed_sessions)

    # Calculate break durations
    all_breaks = db.query(BreakSession).filter(
        BreakSession.attendance_id == attendance.id
    ).all()
    total_break_m = sum(b.duration_minutes for b in all_breaks)
    paid_break_m = sum(b.duration_minutes for b in all_breaks if b.is_paid)
    unpaid_break_m = total_break_m - paid_break_m

    attendance.total_break_minutes = total_break_m
    attendance.paid_break_minutes = paid_break_m
    attendance.unpaid_break_minutes = unpaid_break_m

    # Actual productive working duration
    actual_work_m = max(0, total_session_minutes - unpaid_break_m)
    attendance.actual_working_minutes = actual_work_m
    attendance.work_hours = Decimal(str(round(actual_work_m / 60.0, 2)))

    # Status evaluation against policy
    if actual_work_m >= policy.full_day_minutes:
        attendance.status = "PRESENT"
    elif actual_work_m >= policy.half_day_minutes:
        attendance.status = "HALF_DAY"
    else:
        attendance.status = "HALF_DAY"

    attendance.overtime_minutes = max(0, actual_work_m - policy.full_day_minutes)
    attendance.is_incomplete = False

    db.commit()
    db.refresh(attendance)
    return attendance

def get_today_attendance(employee_id: int, db: Session) -> Optional[Attendance]:
    return db.query(Attendance).options(
        joinedload(Attendance.sessions),
        joinedload(Attendance.breaks)
    ).filter(
        Attendance.employee_id == employee_id,
        Attendance.date == date.today()
    ).first()

def get_live_status(employee_id: int, db: Session) -> AttendanceLiveStatusResponse:
    today = date.today()
    policy = get_policy(db)
    attendance = db.query(Attendance).options(
        joinedload(Attendance.sessions),
        joinedload(Attendance.breaks)
    ).filter(
        Attendance.employee_id == employee_id,
        Attendance.date == today
    ).first()

    if not attendance:
        return AttendanceLiveStatusResponse(
            is_punched_in=False,
            status="NOT_STARTED",
            required_working_minutes=policy.full_day_minutes,
            remaining_working_minutes=policy.full_day_minutes
        )

    active_session = db.query(AttendanceSession).filter(
        AttendanceSession.attendance_id == attendance.id,
        AttendanceSession.punch_out.is_(None)
    ).first()

    active_break = db.query(BreakSession).filter(
        BreakSession.attendance_id == attendance.id,
        BreakSession.break_end.is_(None)
    ).first()

    now = datetime.now()
    # Compute live working minutes
    completed_dur = sum(s.duration_minutes for s in attendance.sessions if s.punch_out is not None)
    current_session_dur = 0
    if active_session:
        current_session_dur = int(round(safe_diff_seconds(now, active_session.punch_in) / 60))

    unpaid_breaks = sum(b.duration_minutes for b in attendance.breaks if not b.is_paid and b.break_end is not None)
    live_working_m = max(0, completed_dur + current_session_dur - unpaid_breaks)

    rem_m = max(0, policy.full_day_minutes - live_working_m)
    overtime_m = max(0, live_working_m - policy.full_day_minutes)

    # Convert sessions and breaks for response
    sessions_resp = [AttendanceSessionResponse.model_validate(s) for s in attendance.sessions]
    breaks_resp = [BreakSessionResponse.model_validate(b) for b in attendance.breaks]

    return AttendanceLiveStatusResponse(
        is_punched_in=active_session is not None,
        active_session_number=active_session.session_number if active_session else None,
        session_punch_in=active_session.punch_in if active_session else None,
        is_on_break=active_break is not None,
        current_break_type=active_break.break_type if active_break else None,
        break_start_time=active_break.break_start if active_break else None,
        first_punch_in=attendance.check_in,
        last_punch_out=attendance.check_out,
        today_working_minutes=live_working_m,
        today_break_minutes=attendance.total_break_minutes,
        office_duration_minutes=attendance.office_duration_minutes,
        required_working_minutes=policy.full_day_minutes,
        remaining_working_minutes=rem_m,
        overtime_minutes=overtime_m,
        status=attendance.status,
        is_late=attendance.is_late,
        total_sessions_count=len(attendance.sessions),
        total_breaks_count=len(attendance.breaks),
        sessions=sessions_resp,
        breaks=breaks_resp
    )

def get_daily_timeline(employee_id: int, target_date: date, db: Session) -> DailyAttendanceTimelineResponse:
    attendance = db.query(Attendance).options(
        joinedload(Attendance.sessions),
        joinedload(Attendance.breaks)
    ).filter(
        Attendance.employee_id == employee_id,
        Attendance.date == target_date
    ).first()

    if not attendance:
        return DailyAttendanceTimelineResponse(
            date=target_date,
            status="ABSENT",
            is_late=False,
            office_duration_hhmm="00:00",
            total_break_hhmm="00:00",
            actual_work_hhmm="00:00",
            overtime_hhmm="00:00",
            events=[]
        )

    events: List[TimelineEvent] = []

    for s in attendance.sessions:
        events.append(TimelineEvent(
            time=s.punch_in.strftime("%I:%M %p"),
            event_type="PUNCH_IN",
            title=f"Punch In (Session #{s.session_number})",
            details="Started work session"
        ))
        if s.punch_out:
            events.append(TimelineEvent(
                time=s.punch_out.strftime("%I:%M %p"),
                event_type="PUNCH_OUT",
                title=f"Punch Out (Session #{s.session_number})",
                details=f"Duration: {format_minutes_to_hhmm(s.duration_minutes)}"
            ))

    for b in attendance.breaks:
        b_type_clean = b.break_type.replace("_", " ").title()
        events.append(TimelineEvent(
            time=b.break_start.strftime("%I:%M %p"),
            event_type="BREAK_START",
            title=f"{b_type_clean} Started",
            details=b.remarks or ("Paid Break" if b.is_paid else "Unpaid Break")
        ))
        if b.break_end:
            events.append(TimelineEvent(
                time=b.break_end.strftime("%I:%M %p"),
                event_type="BREAK_END",
                title=f"{b_type_clean} Ended",
                details=f"Duration: {b.duration_minutes} min"
            ))

    # Sort events by time
    events.sort(key=lambda x: x.time)

    return DailyAttendanceTimelineResponse(
        date=target_date,
        status=attendance.status,
        is_late=attendance.is_late,
        office_duration_hhmm=format_minutes_to_hhmm(attendance.office_duration_minutes),
        total_break_hhmm=format_minutes_to_hhmm(attendance.total_break_minutes),
        actual_work_hhmm=format_minutes_to_hhmm(attendance.actual_working_minutes),
        overtime_hhmm=format_minutes_to_hhmm(attendance.overtime_minutes),
        events=events
    )

def get_weekly_summary(employee_id: int, start_date: Optional[date], db: Session) -> WeeklyAttendanceSummaryResponse:
    if not start_date:
        today = date.today()
        # Find Monday of current week
        start_date = today - timedelta(days=today.weekday())

    end_date = start_date + timedelta(days=6)
    days_items: List[WeeklyDayItem] = []

    total_work_m = 0
    total_break_m = 0

    for i in range(7):
        cur_d = start_date + timedelta(days=i)
        day_name = cur_d.strftime("%A")

        record = db.query(Attendance).filter(
            Attendance.employee_id == employee_id,
            Attendance.date == cur_d
        ).first()

        w_min = record.actual_working_minutes if record else 0
        b_min = record.total_break_minutes if record else 0
        st = record.status if record else ("WEEKLY_OFF" if day_name in ["Saturday", "Sunday"] else "ABSENT")
        is_l = record.is_late if record else False

        total_work_m += w_min
        total_break_m += b_min

        days_items.append(WeeklyDayItem(
            date=cur_d,
            day_name=day_name,
            working_minutes=w_min,
            working_hours_hhmm=format_minutes_to_hhmm(w_min),
            break_minutes=b_min,
            status=st,
            is_late=is_l
        ))

    expected_m = 2400 # 40 hours
    ot_m = max(0, total_work_m - expected_m)

    return WeeklyAttendanceSummaryResponse(
        week_start=start_date,
        week_end=end_date,
        days=days_items,
        total_weekly_working_minutes=total_work_m,
        total_weekly_working_hhmm=format_minutes_to_hhmm(total_work_m),
        total_weekly_break_minutes=total_break_m,
        expected_weekly_minutes=expected_m,
        weekly_overtime_minutes=ot_m
    )

def get_monthly_detailed_summary(employee_id: int, year: int, month: int, db: Session) -> MonthlyAttendanceDetailedResponse:
    num_days = calendar.monthrange(year, month)[1]
    start_d = date(year, month, 1)
    end_d = date(year, month, num_days)

    records = db.query(Attendance).options(
        joinedload(Attendance.sessions),
        joinedload(Attendance.breaks)
    ).filter(
        Attendance.employee_id == employee_id,
        Attendance.date >= start_d,
        Attendance.date <= end_d
    ).all()

    records_by_date = {r.date: r for r in records}

    holidays = {h.date for h in db.query(Holiday).filter(Holiday.date >= start_d, Holiday.date <= end_d).all()}

    leaves = db.query(Leave).filter(
        Leave.employee_id == employee_id,
        Leave.status == "APPROVED",
        Leave.start_date <= end_d,
        Leave.end_date >= start_d
    ).all()

    leave_dates = set()
    for l in leaves:
        curr = max(l.start_date, start_d)
        stop = min(l.end_date, end_d)
        while curr <= stop:
            leave_dates.add(curr)
            curr += timedelta(days=1)

    working_days_count = 0
    present_days = 0
    half_days = 0
    absent_days = 0
    leave_days = len(leave_dates)
    holiday_days = 0
    weekly_off_days = 0

    total_actual_m = 0
    total_break_m = 0
    total_ot_m = 0

    for day_num in range(1, num_days + 1):
        d = date(year, month, day_num)
        is_weekend = d.weekday() in (5, 6) # Sat, Sun
        is_holiday = d in holidays
        is_leave = d in leave_dates

        if is_weekend:
            weekly_off_days += 1
        elif is_holiday:
            holiday_days += 1
        else:
            working_days_count += 1

        rec = records_by_date.get(d)
        if rec:
            total_actual_m += rec.actual_working_minutes
            total_break_m += rec.total_break_minutes
            total_ot_m += rec.overtime_minutes

            if rec.status in {"PRESENT", "LATE"}:
                present_days += 1
            elif rec.status == "HALF_DAY":
                half_days += 1
            elif rec.status == "ABSENT":
                absent_days += 1
        else:
            if not is_weekend and not is_holiday and not is_leave and d <= date.today():
                absent_days += 1

    expected_m = working_days_count * 480 # 8 hours per working day
    rem_m = max(0, expected_m - total_actual_m)
    att_pct = round(((present_days + half_days * 0.5) / working_days_count * 100), 1) if working_days_count > 0 else 0.0

    daily_responses = [AttendanceResponse.model_validate(r) for r in sorted(records, key=lambda x: x.date, reverse=True)]

    return MonthlyAttendanceDetailedResponse(
        year=year,
        month=month,
        total_calendar_days=num_days,
        total_working_days=working_days_count,
        present_days=present_days,
        half_days=half_days,
        absent_days=absent_days,
        approved_leave_days=leave_days,
        holiday_days=holiday_days,
        weekly_off_days=weekly_off_days,
        total_actual_working_minutes=total_actual_m,
        total_actual_working_hhmm=format_minutes_to_hhmm(total_actual_m),
        expected_working_minutes=expected_m,
        expected_working_hhmm=format_minutes_to_hhmm(expected_m),
        remaining_monthly_minutes=rem_m,
        total_break_minutes=total_break_m,
        total_break_hhmm=format_minutes_to_hhmm(total_break_m),
        total_overtime_minutes=total_ot_m,
        total_overtime_hhmm=format_minutes_to_hhmm(total_ot_m),
        attendance_percentage=att_pct,
        daily_records=daily_responses
    )

def get_employee_attendance(
    employee_id: int,
    db: Session,
    page: int = 1,
    size: int = 20,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> PaginatedResponse[AttendanceResponse]:
    query = db.query(Attendance).options(
        joinedload(Attendance.sessions),
        joinedload(Attendance.breaks)
    ).filter(Attendance.employee_id == employee_id)

    if start_date:
        query = query.filter(Attendance.date >= start_date)
    if end_date:
        query = query.filter(Attendance.date <= end_date)

    query = query.order_by(Attendance.date.desc())
    return paginate(query, page, size)

def get_employee_monthly_summary(
    employee_id: int,
    year: int,
    month: int,
    db: Session
) -> AttendanceSummary:
    records = db.query(Attendance).filter(
        Attendance.employee_id == employee_id,
        func.extract("year", Attendance.date) == year,
        func.extract("month", Attendance.date) == month
    ).all()

    total_records = len(records)
    present_days = sum(1 for r in records if r.status in {"PRESENT", "LATE"})
    absent_days = sum(1 for r in records if r.status == "ABSENT")
    late_days = sum(1 for r in records if r.is_late or r.status == "LATE")
    half_days = sum(1 for r in records if r.status == "HALF_DAY")
    total_hours = sum((r.work_hours for r in records), Decimal("0.00"))
    rate = round((present_days / total_records * 100), 1) if total_records > 0 else 0.0

    return AttendanceSummary(
        total_records=total_records,
        present_days=present_days,
        absent_days=absent_days,
        late_days=late_days,
        half_days=half_days,
        total_work_hours=total_hours,
        attendance_rate=rate
    )

def get_all_attendance(
    db: Session,
    page: int = 1,
    size: int = 20,
    date_filter: Optional[date] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    department_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    employee_id: Optional[int] = None
) -> PaginatedResponse[AttendanceResponse]:
    query = db.query(Attendance).options(
        joinedload(Attendance.employee),
        joinedload(Attendance.sessions),
        joinedload(Attendance.breaks)
    )

    if employee_id:
        query = query.filter(Attendance.employee_id == employee_id)
    if date_filter:
        query = query.filter(Attendance.date == date_filter)
    if start_date:
        query = query.filter(Attendance.date >= start_date)
    if end_date:
        query = query.filter(Attendance.date <= end_date)
    if status_filter:
        query = query.filter(Attendance.status == status_filter.upper())
    if department_id:
        query = query.join(Employee, Employee.id == Attendance.employee_id).filter(
            Employee.department_id == department_id
        )

    query = query.order_by(Attendance.date.desc(), Attendance.id.desc())
    return paginate(query, page, size)

def manual_record_attendance(data: AttendanceManualCreate, db: Session) -> Attendance:
    employee = db.query(Employee).filter(Employee.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    existing = db.query(Attendance).filter(
        Attendance.employee_id == data.employee_id,
        Attendance.date == data.date
    ).first()

    hours = calculate_work_hours(data.check_in, data.check_out)
    is_late = (data.check_in > STANDARD_START_TIME) if data.check_in else False
    work_m = int(round(float(hours) * 60))

    try:
        if existing:
            existing.check_in = data.check_in
            existing.check_out = data.check_out
            existing.work_hours = hours
            existing.actual_working_minutes = work_m
            existing.office_duration_minutes = work_m
            existing.status = data.status
            existing.is_late = is_late
            existing.remarks = data.remarks or "Manually adjusted by admin"
            db.commit()
            db.refresh(existing)
            return existing
        else:
            attendance = Attendance(
                employee_id=data.employee_id,
                date=data.date,
                check_in=data.check_in,
                check_out=data.check_out,
                work_hours=hours,
                actual_working_minutes=work_m,
                office_duration_minutes=work_m,
                is_late=is_late,
                status=data.status,
                remarks=data.remarks or "Manual entry by admin"
            )
            db.add(attendance)
            db.commit()
            db.refresh(attendance)
            return attendance
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record manual attendance: {str(exc)}"
        )

def correct_attendance(attendance_id: int, data: AttendanceUpdate, db: Session) -> Attendance:
    attendance = db.query(Attendance).filter(Attendance.id == attendance_id).first()
    if not attendance:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    if data.check_in is not None:
        attendance.check_in = data.check_in
        attendance.is_late = data.check_in > STANDARD_START_TIME
    if data.check_out is not None:
        attendance.check_out = data.check_out
    if data.status is not None:
        attendance.status = data.status
    if data.remarks is not None:
        attendance.remarks = data.remarks

    attendance.work_hours = calculate_work_hours(attendance.check_in, attendance.check_out)
    attendance.actual_working_minutes = int(round(float(attendance.work_hours) * 60))
    attendance.office_duration_minutes = attendance.actual_working_minutes

    try:
        db.commit()
        db.refresh(attendance)
        return attendance
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to correct attendance: {str(exc)}"
        )

def get_daily_report(report_date: date, db: Session) -> DailyAttendanceReport:
    total_active_employees = db.query(Employee).filter(
        Employee.employment_status == "ACTIVE"
    ).count()

    records = db.query(Attendance).filter(Attendance.date == report_date).all()
    present = sum(1 for r in records if r.status == "PRESENT")
    late = sum(1 for r in records if r.status == "LATE" or r.is_late)
    half_day = sum(1 for r in records if r.status == "HALF_DAY")
    attended_count = len(records)
    absent = max(0, total_active_employees - attended_count)
    rate = round((attended_count / total_active_employees * 100), 1) if total_active_employees > 0 else 0.0

    return DailyAttendanceReport(
        date=report_date,
        total_employees=total_active_employees,
        present=present,
        absent=absent,
        late=late,
        half_day=half_day,
        attendance_rate=rate
    )

# Regularization / Correction requests
def create_correction_request(employee_id: int, data: AttendanceCorrectionCreate, db: Session) -> AttendanceCorrection:
    attendance = db.query(Attendance).filter(
        Attendance.id == data.attendance_id,
        Attendance.employee_id == employee_id
    ).first()

    if not attendance:
        raise HTTPException(status_code=404, detail="Attendance record not found for your account")

    existing_pending = db.query(AttendanceCorrection).filter(
        AttendanceCorrection.attendance_id == data.attendance_id,
        AttendanceCorrection.status == "PENDING"
    ).first()

    if existing_pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have a pending correction request for this attendance record."
        )

    corr = AttendanceCorrection(
        attendance_id=data.attendance_id,
        employee_id=employee_id,
        requested_check_in=data.requested_check_in,
        requested_check_out=data.requested_check_out,
        reason=data.reason,
        status="PENDING"
    )
    db.add(corr)
    db.commit()
    db.refresh(corr)
    return corr

def get_employee_corrections(employee_id: int, db: Session) -> List[AttendanceCorrection]:
    return db.query(AttendanceCorrection).filter(
        AttendanceCorrection.employee_id == employee_id
    ).order_by(AttendanceCorrection.id.desc()).all()

def get_pending_corrections(db: Session) -> List[AttendanceCorrection]:
    return db.query(AttendanceCorrection).filter(
        AttendanceCorrection.status == "PENDING"
    ).order_by(AttendanceCorrection.id.desc()).all()

def review_correction_request(
    correction_id: int,
    admin_user_id: int,
    data: AttendanceCorrectionReview,
    db: Session
) -> AttendanceCorrection:
    corr = db.query(AttendanceCorrection).filter(AttendanceCorrection.id == correction_id).first()
    if not corr:
        raise HTTPException(status_code=404, detail="Correction request not found")

    if corr.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Request is already {corr.status.lower()}")

    corr.status = data.status
    corr.reviewed_by = admin_user_id
    corr.review_remarks = data.review_remarks

    if data.status == "APPROVED":
        # Apply the correction to the attendance record
        att = db.query(Attendance).filter(Attendance.id == corr.attendance_id).first()
        if att:
            if corr.requested_check_in is not None:
                att.check_in = corr.requested_check_in
                policy = get_policy(db)
                att.is_late = corr.requested_check_in > policy.late_threshold_time
            if corr.requested_check_out is not None:
                att.check_out = corr.requested_check_out

            att.work_hours = calculate_work_hours(att.check_in, att.check_out)
            att.actual_working_minutes = int(round(float(att.work_hours) * 60))
            att.office_duration_minutes = att.actual_working_minutes
            att.is_incomplete = False
            att.remarks = f"Corrected via Regularization Request #{corr.id}: {data.review_remarks}"

    # Log action in audit log
    audit = AuditLog(
        user_id=admin_user_id,
        action="REVIEW_ATTENDANCE_CORRECTION",
        resource_type="AttendanceCorrection",
        resource_id=str(corr.id),
        details=f"Correction status set to {data.status}. Remarks: {data.review_remarks}"
    )
    db.add(audit)
    db.commit()
    db.refresh(corr)
    return corr
