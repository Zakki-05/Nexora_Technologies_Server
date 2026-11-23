from datetime import date, datetime, timedelta, time
from decimal import Decimal
import pytest
from fastapi import HTTPException

from app.models.user import User
from app.models.department import Department
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.attendance_session import AttendanceSession
from app.models.break_session import BreakSession
from app.models.attendance_policy import AttendancePolicy
from app.models.leave_balance import LeaveBalance
from app.services import attendance_service, break_service
from app.schemas.attendance import (
    AttendanceCorrectionCreate,
    AttendanceCorrectionReview
)
from app.utils.security import hash_password

@pytest.fixture
def multi_session_setup(db_session):
    admin = User(
        username="super_lead",
        email="super_lead@ems.com",
        hashed_password=hash_password("SuperPass123!"),
        role="SUPER_ADMIN",
        is_active=True
    )
    emp_user = User(
        username="rahul_emp",
        email="rahul@ems.com",
        hashed_password=hash_password("RahulPass123!"),
        role="EMPLOYEE",
        is_active=True
    )
    dept = Department(name="Engineering", description="Software & Systems")
    db_session.add_all([admin, emp_user, dept])
    db_session.commit()

    employee = Employee(
        user_id=emp_user.id,
        department_id=dept.id,
        employee_code="EMP-7777",
        full_name="Rahul Sharma",
        phone="+919876543299",
        hire_date=date(2026, 1, 1),
        position="Senior Developer",
        salary=Decimal("75000.00"),
        employment_status="ACTIVE"
    )
    db_session.add(employee)
    db_session.commit()
    db_session.refresh(employee)

    policy = AttendancePolicy(
        policy_name="Test Policy",
        office_start_time=time(9, 0),
        office_end_time=time(18, 0),
        grace_period_minutes=30,
        late_threshold_time=time(9, 30),
        full_day_minutes=480,
        half_day_minutes=240,
        max_daily_break_minutes=90,
        paid_break_types="TEA_BREAK,SHORT_BREAK",
        unpaid_break_types="LUNCH_BREAK,PERSONAL_BREAK,OTHER_BREAK",
        is_active=True
    )
    db_session.add(policy)
    db_session.commit()

    return {"admin": admin, "employee": employee, "policy": policy}

def test_multiple_working_sessions_same_day(db_session, multi_session_setup):
    emp = multi_session_setup["employee"]
    today = date.today()

    # Session 1: Punch In and Out
    att1 = attendance_service.check_in(emp.id, db_session)
    assert att1.date == today
    s1 = db_session.query(AttendanceSession).filter(AttendanceSession.attendance_id == att1.id).first()
    assert s1 is not None
    assert s1.session_number == 1
    assert s1.punch_out is None

    # Cannot punch in again while session 1 active
    with pytest.raises(HTTPException) as exc:
        attendance_service.check_in(emp.id, db_session)
    assert exc.value.status_code == 400

    # Punch out session 1
    att1 = attendance_service.check_out(emp.id, db_session)
    assert att1.is_incomplete is False
    db_session.refresh(s1)
    assert s1.punch_out is not None

    # Session 2: Punch in again on the SAME day!
    att2 = attendance_service.check_in(emp.id, db_session)
    assert att2.id == att1.id # Must be the exact same attendance day record!
    sessions = db_session.query(AttendanceSession).filter(AttendanceSession.attendance_id == att2.id).all()
    assert len(sessions) == 2
    assert sessions[1].session_number == 2

    # Punch out session 2
    att2 = attendance_service.check_out(emp.id, db_session)
    assert len(att2.sessions) == 2

    # Session 3: Punch in again on the SAME day!
    att3 = attendance_service.check_in(emp.id, db_session)
    assert att3.id == att1.id
    sessions = db_session.query(AttendanceSession).filter(AttendanceSession.attendance_id == att3.id).all()
    assert len(sessions) == 3

    att3 = attendance_service.check_out(emp.id, db_session)
    assert len(att3.sessions) == 3

def test_break_management_start_and_end(db_session, multi_session_setup):
    emp = multi_session_setup["employee"]

    # Starting a break before punch in must fail
    with pytest.raises(HTTPException) as exc:
        break_service.start_break(emp.id, "TEA_BREAK", "Tea time", db_session)
    assert exc.value.status_code == 400

    # Punch in
    attendance_service.check_in(emp.id, db_session)

    # Start Tea Break (Paid)
    b1 = break_service.start_break(emp.id, "TEA_BREAK", "Quick morning tea", db_session)
    assert b1.id is not None
    assert b1.break_type == "TEA_BREAK"
    assert b1.is_paid is True
    assert b1.break_end is None

    # Attempt to start another break while active must fail
    with pytest.raises(HTTPException) as exc:
        break_service.start_break(emp.id, "LUNCH_BREAK", "Lunch", db_session)
    assert exc.value.status_code == 400

    # End Tea Break
    b1_ended = break_service.end_break(emp.id, db_session)
    assert b1_ended.break_end is not None
    assert b1_ended.duration_minutes >= 1

    # Start Lunch Break (Unpaid)
    b2 = break_service.start_break(emp.id, "LUNCH_BREAK", "Afternoon lunch", db_session)
    assert b2.break_type == "LUNCH_BREAK"
    assert b2.is_paid is False

    b2_ended = break_service.end_break(emp.id, db_session)
    assert b2_ended.duration_minutes >= 1

    # Check break status
    status_resp = break_service.get_break_status(emp.id, db_session)
    assert status_resp.is_on_break is False
    assert status_resp.breaks_taken_count == 2
    assert status_resp.total_break_minutes >= 2

def test_daily_timeline_generation(db_session, multi_session_setup):
    emp = multi_session_setup["employee"]
    today = date.today()

    # Punch in
    attendance_service.check_in(emp.id, db_session)
    # Start break
    break_service.start_break(emp.id, "TEA_BREAK", "Tea", db_session)
    # End break
    break_service.end_break(emp.id, db_session)
    # Punch out
    attendance_service.check_out(emp.id, db_session)

    timeline = attendance_service.get_daily_timeline(emp.id, today, db_session)
    assert timeline.date == today
    assert len(timeline.events) >= 4 # In, Break Start, Break End, Out

def test_live_status_response(db_session, multi_session_setup):
    emp = multi_session_setup["employee"]

    # Before punch in
    st_before = attendance_service.get_live_status(emp.id, db_session)
    assert st_before.is_punched_in is False

    # Punch in
    attendance_service.check_in(emp.id, db_session)
    st_working = attendance_service.get_live_status(emp.id, db_session)
    assert st_working.is_punched_in is True
    assert st_working.active_session_number == 1
    assert st_working.is_on_break is False

    # Start break
    break_service.start_break(emp.id, "TEA_BREAK", "Snack", db_session)
    st_breaking = attendance_service.get_live_status(emp.id, db_session)
    assert st_breaking.is_on_break is True
    assert st_breaking.current_break_type == "TEA_BREAK"

    # End break and punch out
    break_service.end_break(emp.id, db_session)
    attendance_service.check_out(emp.id, db_session)
    st_after = attendance_service.get_live_status(emp.id, db_session)
    assert st_after.is_punched_in is False

def test_weekly_and_monthly_aggregation(db_session, multi_session_setup):
    emp = multi_session_setup["employee"]
    today = date.today()

    # Record attendance
    attendance_service.check_in(emp.id, db_session)
    attendance_service.check_out(emp.id, db_session)

    # Weekly summary
    weekly = attendance_service.get_weekly_summary(emp.id, None, db_session)
    assert len(weekly.days) == 7
    assert weekly.total_weekly_working_minutes >= 0

    # Monthly detailed summary
    monthly = attendance_service.get_monthly_detailed_summary(emp.id, today.year, today.month, db_session)
    assert monthly.year == today.year
    assert monthly.month == today.month
    assert monthly.total_calendar_days in {28, 29, 30, 31}
    assert (monthly.present_days + monthly.half_days) >= 1

def test_attendance_regularization_workflow(db_session, multi_session_setup):
    emp = multi_session_setup["employee"]
    admin = multi_session_setup["admin"]

    # Create an attendance record
    att = attendance_service.check_in(emp.id, db_session)
    attendance_service.check_out(emp.id, db_session)

    # Employee submits correction request
    corr_data = AttendanceCorrectionCreate(
        attendance_id=att.id,
        requested_check_in=time(9, 15),
        requested_check_out=time(18, 15),
        reason="Forgot to punch out due to client emergency meeting"
    )
    corr = attendance_service.create_correction_request(emp.id, corr_data, db_session)
    assert corr.status == "PENDING"
    assert corr.employee_id == emp.id

    # Duplicate correction request on same record fails
    with pytest.raises(HTTPException) as exc:
        attendance_service.create_correction_request(emp.id, corr_data, db_session)
    assert exc.value.status_code == 400

    # Admin reviews and approves
    review_data = AttendanceCorrectionReview(
        status="APPROVED",
        review_remarks="Approved based on client meeting notes"
    )
    reviewed = attendance_service.review_correction_request(corr.id, admin.id, review_data, db_session)
    assert reviewed.status == "APPROVED"
    assert reviewed.reviewed_by == admin.id

    # Verify attendance record was updated
    db_session.refresh(att)
    assert att.check_in == time(9, 15)
    assert att.check_out == time(18, 15)
    assert "Approved based on client meeting notes" in att.remarks
