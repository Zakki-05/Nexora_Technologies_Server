from datetime import date, time, timedelta
from decimal import Decimal
import pytest
from fastapi import HTTPException

from app.models.user import User
from app.models.department import Department
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.leave import Leave
from app.models.leave_balance import LeaveBalance
from app.schemas.attendance import AttendanceManualCreate, AttendanceUpdate
from app.schemas.leave import LeaveCreate, LeaveDecision, LeaveBalanceUpdate
from app.services.attendance_service import (
    check_in,
    check_out,
    get_today_attendance,
    get_employee_attendance,
    get_employee_monthly_summary,
    manual_record_attendance,
    correct_attendance,
    calculate_work_hours
)
from app.services.leave_service import (
    apply_leave,
    get_employee_leaves,
    review_leave,
    cancel_leave,
    get_employee_balance,
    update_employee_balance
)
from app.utils.security import hash_password

@pytest.fixture
def ems_setup(db_session):
    admin = User(
        username="admin_lead",
        email="lead@ems.com",
        hashed_password=hash_password("LeadPass123!"),
        role="ADMIN",
        is_active=True
    )
    emp_user = User(
        username="worker_bob",
        email="bob@ems.com",
        hashed_password=hash_password("BobPass123!"),
        role="EMPLOYEE",
        is_active=True
    )
    dept = Department(name="Logistics", description="Global logistics")
    db_session.add_all([admin, emp_user, dept])
    db_session.commit()

    employee = Employee(
        user_id=emp_user.id,
        department_id=dept.id,
        employee_code="EMP-8888",
        full_name="Bob Worker",
        phone="+14444444444",
        hire_date=date(2026, 1, 1),
        position="Coordinator",
        salary=Decimal("55000.00"),
        employment_status="ACTIVE"
    )
    db_session.add(employee)
    db_session.commit()
    db_session.refresh(employee)

    balance = LeaveBalance(
        employee_id=employee.id,
        annual_total=15,
        annual_used=0,
        sick_total=10,
        sick_used=0,
        casual_total=10,
        casual_used=0,
        unpaid_used=0
    )
    db_session.add(balance)
    db_session.commit()

    return {"admin": admin, "emp_user": emp_user, "employee": employee, "balance": balance}

# ================= ATTENDANCE TESTS =================

def test_check_in_and_duplicate_prevention(db_session, ems_setup):
    emp = ems_setup["employee"]
    record = check_in(emp.id, db_session)
    assert record.id is not None
    assert record.employee_id == emp.id
    assert record.date == date.today()
    assert record.check_in is not None
    assert record.check_out is None

    # Duplicate check in today fails
    with pytest.raises(HTTPException) as exc:
        check_in(emp.id, db_session)
    assert exc.value.status_code in {400, 409}

def test_check_out_and_work_hours(db_session, ems_setup):
    emp = ems_setup["employee"]
    # Check in first
    check_in(emp.id, db_session)

    # Check out
    out_record = check_out(emp.id, db_session)
    assert out_record.check_out is not None

    # Duplicate check out fails
    with pytest.raises(HTTPException) as exc:
        check_out(emp.id, db_session)
    assert exc.value.status_code in {400, 409}

def test_check_out_without_check_in_fails(db_session, ems_setup):
    emp = ems_setup["employee"]
    with pytest.raises(HTTPException) as exc:
        check_out(emp.id, db_session)
    assert exc.value.status_code == 404

def test_calculate_work_hours():
    t1 = time(9, 0, 0)
    t2 = time(17, 30, 0)
    hours = calculate_work_hours(t1, t2)
    assert hours == Decimal("8.50")

def test_manual_attendance_and_correction(db_session, ems_setup):
    emp = ems_setup["employee"]
    past_date = date.today() - timedelta(days=2)

    data = AttendanceManualCreate(
        employee_id=emp.id,
        date=past_date,
        check_in=time(9, 0, 0),
        check_out=time(17, 0, 0),
        status="PRESENT",
        remarks="Manual entry for testing"
    )
    record = manual_record_attendance(data, db_session)
    assert record.work_hours == Decimal("8.00")
    assert record.status == "PRESENT"

    # Admin corrects check_out time to 18:00
    corr = AttendanceUpdate(check_out=time(18, 0, 0))
    updated = correct_attendance(record.id, corr, db_session)
    assert updated.check_out == time(18, 0, 0)
    assert updated.work_hours == Decimal("9.00")

# ================= LEAVE TESTS =================

def test_apply_leave_success(db_session, ems_setup):
    emp = ems_setup["employee"]
    start = date.today() + timedelta(days=5)
    end = date.today() + timedelta(days=7)

    leave_data = LeaveCreate(
        leave_type="Annual",
        start_date=start,
        end_date=end,
        reason="Vacation trip"
    )
    leave = apply_leave(emp.id, leave_data, db_session)
    assert leave.id is not None
    assert leave.days_count == 3
    assert leave.status == "PENDING"

def test_apply_leave_overlapping_fails(db_session, ems_setup):
    emp = ems_setup["employee"]
    start = date.today() + timedelta(days=10)
    end = date.today() + timedelta(days=15)

    leave_data1 = LeaveCreate(
        leave_type="Annual",
        start_date=start,
        end_date=end,
        reason="First request"
    )
    apply_leave(emp.id, leave_data1, db_session)

    # Overlapping request
    leave_data2 = LeaveCreate(
        leave_type="Sick",
        start_date=start + timedelta(days=2),
        end_date=end + timedelta(days=2),
        reason="Overlapping request"
    )
    with pytest.raises(HTTPException) as exc:
        apply_leave(emp.id, leave_data2, db_session)
    assert exc.value.status_code == 409

def test_apply_leave_exceeding_balance_fails(db_session, ems_setup):
    emp = ems_setup["employee"]
    # Total annual is 15. Attempt 20 days.
    start = date.today() + timedelta(days=30)
    end = start + timedelta(days=19)  # 20 days inclusive

    leave_data = LeaveCreate(
        leave_type="Annual",
        start_date=start,
        end_date=end,
        reason="Extended holiday"
    )
    with pytest.raises(HTTPException) as exc:
        apply_leave(emp.id, leave_data, db_session)
    assert exc.value.status_code == 400

def test_approve_leave_and_balance_deduction(db_session, ems_setup):
    emp = ems_setup["employee"]
    admin = ems_setup["admin"]

    start = date.today() + timedelta(days=20)
    end = date.today() + timedelta(days=22)  # 3 days

    leave = apply_leave(emp.id, LeaveCreate(
        leave_type="Annual",
        start_date=start,
        end_date=end,
        reason="Family event"
    ), db_session)

    # Admin approves
    decision = LeaveDecision(status="APPROVED")
    approved = review_leave(leave.id, decision, admin.id, db_session)
    assert approved.status == "APPROVED"
    assert approved.approved_by == admin.id

    # Verify balance was deducted
    balance = get_employee_balance(emp.id, db_session)
    assert balance.annual_used == 3
    assert balance.annual_remaining == 12

def test_reject_leave_with_reason(db_session, ems_setup):
    emp = ems_setup["employee"]
    admin = ems_setup["admin"]

    start = date.today() + timedelta(days=40)
    end = date.today() + timedelta(days=41)

    leave = apply_leave(emp.id, LeaveCreate(
        leave_type="Casual",
        start_date=start,
        end_date=end,
        reason="Personal issue"
    ), db_session)

    decision = LeaveDecision(status="REJECTED", rejection_reason="Critical sprint deadline")
    rejected = review_leave(leave.id, decision, admin.id, db_session)
    assert rejected.status == "REJECTED"
    assert rejected.rejection_reason == "Critical sprint deadline"

    # Casual balance untouched
    balance = get_employee_balance(emp.id, db_session)
    assert balance.casual_used == 0

def test_review_already_processed_leave_fails(db_session, ems_setup):
    emp = ems_setup["employee"]
    admin = ems_setup["admin"]

    start = date.today() + timedelta(days=50)
    end = date.today() + timedelta(days=50)

    leave = apply_leave(emp.id, LeaveCreate(
        leave_type="Sick",
        start_date=start,
        end_date=end,
        reason="Cold"
    ), db_session)

    review_leave(leave.id, LeaveDecision(status="APPROVED"), admin.id, db_session)

    # Second review attempt fails
    with pytest.raises(HTTPException) as exc:
        review_leave(leave.id, LeaveDecision(status="REJECTED", rejection_reason="Changed mind"), admin.id, db_session)
    assert exc.value.status_code == 409

def test_cancel_pending_leave_by_employee(db_session, ems_setup):
    emp = ems_setup["employee"]

    start = date.today() + timedelta(days=60)
    end = date.today() + timedelta(days=61)

    leave = apply_leave(emp.id, LeaveCreate(
        leave_type="Casual",
        start_date=start,
        end_date=end,
        reason="Going to cancel this"
    ), db_session)

    cancelled = cancel_leave(leave.id, emp.id, db_session)
    assert cancelled.status == "CANCELLED"
