from datetime import date, timedelta
from decimal import Decimal
import pytest
from fastapi import HTTPException

from app.models.user import User
from app.models.department import Department
from app.models.employee import Employee
from app.models.holiday import Holiday
from app.models.leave_type import LeaveType
from app.models.leave_transaction import LeaveTransaction
from app.schemas.leave import (
    LeaveCreate,
    LeaveDecision,
    LeaveTypeCreate,
    LeaveTypeUpdate,
    LeaveAdjustmentRequest
)
from app.services.leave_service import (
    apply_leave,
    review_leave,
    cancel_leave,
    adjust_leave_balance,
    get_leave_ledger,
    get_employee_balance,
    calculate_leave_days,
    get_all_leave_types,
    create_leave_type,
    update_leave_type,
    delete_leave_type,
    ensure_standard_leave_types
)
from app.utils.security import hash_password

@pytest.fixture
def leave_ledger_fixture(db_session):
    admin_user = User(
        username="lead_admin_leave",
        email="lead_admin_leave@ems.com",
        hashed_password=hash_password("LeadAdmin123!"),
        role="ADMIN",
        is_active=True
    )
    emp_user = User(
        username="staff_member",
        email="staff_member@ems.com",
        hashed_password=hash_password("StaffPass123!"),
        role="EMPLOYEE",
        is_active=True
    )
    dept = Department(name="Leave Ops", description="Operations department")
    db_session.add_all([admin_user, emp_user, dept])
    db_session.commit()

    admin_emp = Employee(
        user_id=admin_user.id,
        department_id=dept.id,
        employee_code="EMP-9001",
        full_name="Lead Admin Officer",
        phone="+15555550001",
        hire_date=date(2026, 1, 1),
        position="Administrator",
        salary=Decimal("80000.00"),
        employment_status="ACTIVE"
    )
    staff_emp = Employee(
        user_id=emp_user.id,
        department_id=dept.id,
        employee_code="EMP-9002",
        full_name="Staff Worker",
        phone="+15555550002",
        hire_date=date(2026, 1, 1),
        position="Staff Specialist",
        salary=Decimal("50000.00"),
        employment_status="ACTIVE"
    )
    db_session.add_all([admin_emp, staff_emp])
    db_session.commit()
    db_session.refresh(admin_emp)
    db_session.refresh(staff_emp)

    ensure_standard_leave_types(db_session)

    return {
        "admin_user": admin_user,
        "admin_emp": admin_emp,
        "emp_user": emp_user,
        "staff_emp": staff_emp
    }

# ==================== TEST SUITE ====================

def test_10_corporate_leave_types_seeded_and_crud(db_session, leave_ledger_fixture):
    # Verify standard types exist
    types = get_all_leave_types(db_session, active_only=True)
    type_codes = {t.code for t in types}
    assert "ANNUAL_LEAVE" in type_codes
    assert "SICK_LEAVE" in type_codes
    assert "CASUAL_LEAVE" in type_codes
    assert "UNPAID_LEAVE" in type_codes

    # Create a custom corporate leave type
    custom_type = create_leave_type(LeaveTypeCreate(
        name="Study Sabbatical",
        code="STUDY_SABBATICAL",
        description="Higher education sabbatical leave",
        annual_allocation=30,
        is_paid=False,
        carry_forward_enabled=False,
        max_consecutive_days=60,
        requires_document=True,
        allow_half_day=False,
        is_active=True
    ), db_session)

    assert custom_type.id is not None
    assert custom_type.code == "STUDY_SABBATICAL"

    # Update the type
    updated = update_leave_type(custom_type.id, LeaveTypeUpdate(
        description="Updated higher education sabbatical leave",
        annual_allocation=45
    ), db_session)
    assert updated.annual_allocation == 45
    assert "Updated" in updated.description

    # Delete the custom type
    delete_res = delete_leave_type(custom_type.id, db_session)
    assert delete_res["success"] is True

def test_leave_reservation_vs_approved_deduction_ledger(db_session, leave_ledger_fixture):
    staff = leave_ledger_fixture["staff_emp"]
    admin = leave_ledger_fixture["admin_user"]

    # Initial balance check
    bal_initial = get_employee_balance(staff.id, db_session)
    annual_initial = next(t for t in bal_initial.type_balances if t.leave_type_code == "ANNUAL_LEAVE")
    assert annual_initial.annual_allocation == 18.0
    assert annual_initial.available == 18.0
    assert annual_initial.approved_consumed == 0.0
    assert annual_initial.pending_reserved == 0.0

    # 1. Apply for 3 days of Annual Leave
    start_d = date.today() + timedelta(days=10)
    end_d = date.today() + timedelta(days=12)  # 3 days
    leave_req = apply_leave(staff.id, LeaveCreate(
        leave_type="ANNUAL_LEAVE",
        start_date=start_d,
        end_date=end_d,
        reason="Family vacation"
    ), db_session)

    assert leave_req.id is not None
    assert leave_req.status == "PENDING"
    assert leave_req.days_count == 3.0

    # Check that balance now has pending reservation, but NOT permanent deduction
    bal_pending = get_employee_balance(staff.id, db_session)
    annual_pending = next(t for t in bal_pending.type_balances if t.leave_type_code == "ANNUAL_LEAVE")
    assert annual_pending.pending_reserved == 3.0
    assert annual_pending.approved_consumed == 0.0
    assert annual_pending.available == 15.0

    # 2. Admin approves the request
    approved_leave = review_leave(
        leave_id=leave_req.id,
        data=LeaveDecision(status="APPROVED"),
        admin_user_id=admin.id,
        db=db_session
    )
    assert approved_leave.status == "APPROVED"
    assert approved_leave.approved_by == admin.id

    # Check ledger transaction created
    ledger = get_leave_ledger(staff.id, db_session)
    deduction_tx = next(t for t in ledger.items if t.transaction_type == "APPROVAL_DEDUCTION")
    assert deduction_tx.days == 3.0
    assert deduction_tx.reference_id == f"APPR-LEAVE-{leave_req.id}"
    assert deduction_tx.balance_after == 15.0

    # Check balances after approval
    bal_approved = get_employee_balance(staff.id, db_session)
    annual_appr = next(t for t in bal_approved.type_balances if t.leave_type_code == "ANNUAL_LEAVE")
    assert annual_appr.pending_reserved == 0.0
    assert annual_appr.approved_consumed == 3.0
    assert annual_appr.available == 15.0

    # Double approval must be rejected
    with pytest.raises(HTTPException) as exc:
        review_leave(leave_req.id, LeaveDecision(status="APPROVED"), admin.id, db_session)
    assert exc.value.status_code == 409

def test_admin_rejection_releases_pending_reservation_without_deduction(db_session, leave_ledger_fixture):
    staff = leave_ledger_fixture["staff_emp"]
    admin = leave_ledger_fixture["admin_user"]

    start_d = date.today() + timedelta(days=25)
    end_d = date.today() + timedelta(days=26)  # 2 days

    leave_req = apply_leave(staff.id, LeaveCreate(
        leave_type="Casual Leave",
        start_date=start_d,
        end_date=end_d,
        reason="Need 2 casual days"
    ), db_session)

    bal_before_reject = get_employee_balance(staff.id, db_session)
    casual_before = next(t for t in bal_before_reject.type_balances if t.leave_type_code == "CASUAL_LEAVE")
    assert casual_before.pending_reserved == 2.0
    assert casual_before.available == 8.0  # 10 - 2

    # Admin rejects with remarks
    rejected_leave = review_leave(
        leave_id=leave_req.id,
        data=LeaveDecision(status="REJECTED", rejection_reason="Quarterly audit in progress"),
        admin_user_id=admin.id,
        db=db_session
    )
    assert rejected_leave.status == "REJECTED"
    assert rejected_leave.rejection_reason == "Quarterly audit in progress"

    # Verify balance was completely restored (pending reservation released)
    bal_after_reject = get_employee_balance(staff.id, db_session)
    casual_after = next(t for t in bal_after_reject.type_balances if t.leave_type_code == "CASUAL_LEAVE")
    assert casual_after.pending_reserved == 0.0
    assert casual_after.approved_consumed == 0.0
    assert casual_after.available == 10.0

def test_cancel_approved_leave_creates_cancellation_refund_transaction(db_session, leave_ledger_fixture):
    staff = leave_ledger_fixture["staff_emp"]
    admin = leave_ledger_fixture["admin_user"]

    start_d = date.today() + timedelta(days=35)
    end_d = date.today() + timedelta(days=36)  # 2 days

    leave_req = apply_leave(staff.id, LeaveCreate(
        leave_type="Sick Leave",
        start_date=start_d,
        end_date=end_d,
        reason="Medical procedure"
    ), db_session)

    # Approve
    review_leave(leave_req.id, LeaveDecision(status="APPROVED"), admin.id, db_session)

    bal_appr = get_employee_balance(staff.id, db_session)
    sick_appr = next(t for t in bal_appr.type_balances if t.leave_type_code == "SICK_LEAVE")
    assert sick_appr.approved_consumed == 2.0
    assert sick_appr.available == 10.0  # 12 - 2

    # Employee or Admin cancels the approved leave
    cancelled = cancel_leave(leave_req.id, staff.id, db_session)
    assert cancelled.status == "CANCELLED"

    # Verify CANCELLATION_REFUND was recorded in ledger
    ledger = get_leave_ledger(staff.id, db_session)
    refund_tx = next(t for t in ledger.items if t.transaction_type == "CANCELLATION_REFUND")
    assert refund_tx.days == 2.0
    assert refund_tx.reference_id == f"CANC-LEAVE-{leave_req.id}"

    # Balance is fully restored
    bal_restored = get_employee_balance(staff.id, db_session)
    sick_restored = next(t for t in bal_restored.type_balances if t.leave_type_code == "SICK_LEAVE")
    assert sick_restored.approved_consumed == 0.0
    assert sick_restored.available == 12.0

def test_half_day_leave_workflow_and_session_overlap(db_session, leave_ledger_fixture):
    staff = leave_ledger_fixture["staff_emp"]

    target_date = date.today() + timedelta(days=45)

    # 1. Apply for FIRST_HALF
    first_half = apply_leave(staff.id, LeaveCreate(
        leave_type="Casual Leave",
        start_date=target_date,
        end_date=target_date,
        is_half_day=True,
        half_day_session="FIRST_HALF",
        reason="Morning doctor appointment"
    ), db_session)
    assert first_half.days_count == 0.5
    assert first_half.is_half_day is True
    assert first_half.half_day_session == "FIRST_HALF"

    # 2. Applying for duplicate FIRST_HALF on same date must fail with 409
    with pytest.raises(HTTPException) as exc:
        apply_leave(staff.id, LeaveCreate(
            leave_type="Casual Leave",
            start_date=target_date,
            end_date=target_date,
            is_half_day=True,
            half_day_session="FIRST_HALF",
            reason="Another morning request"
        ), db_session)
    assert exc.value.status_code == 409

    # 3. Applying for SECOND_HALF on the same date should succeed!
    second_half = apply_leave(staff.id, LeaveCreate(
        leave_type="Casual Leave",
        start_date=target_date,
        end_date=target_date,
        is_half_day=True,
        half_day_session="SECOND_HALF",
        reason="Afternoon personal appointment"
    ), db_session)
    assert second_half.days_count == 0.5
    assert second_half.half_day_session == "SECOND_HALF"

def test_weekend_and_holiday_exclusion(db_session):
    # Friday 2026-11-27 to Monday 2026-11-30:
    # Nov 27 (Fri), Nov 28 (Sat), Nov 29 (Sun), Nov 30 (Mon) -> 4 calendar days
    fri = date(2026, 11, 27)
    mon = date(2026, 11, 30)

    # Simple calendar calculation: 4 days
    days_cal = calculate_leave_days(fri, mon, is_half_day=False, exclude_weekends=False, db=None)
    assert days_cal == 4.0

    # With weekend exclusion: Fri + Mon = 2 days
    days_weekends_excl = calculate_leave_days(fri, mon, is_half_day=False, exclude_weekends=True, db=None)
    assert days_weekends_excl == 2.0

    # With corporate holiday on Friday: only Monday = 1 day
    holiday = Holiday(name="Test Corporate Holiday", date=fri, is_optional=False)
    db_session.add(holiday)
    db_session.commit()

    days_holiday_excl = calculate_leave_days(fri, mon, is_half_day=False, exclude_weekends=True, db=db_session)
    assert days_holiday_excl == 1.0

def test_manual_adjustment_and_self_approval_prevention(db_session, leave_ledger_fixture):
    staff = leave_ledger_fixture["staff_emp"]
    admin = leave_ledger_fixture["admin_user"]
    admin_emp = leave_ledger_fixture["admin_emp"]

    # 1. Admin grants 2 days of Compensatory Off to Staff
    comp_off_type = db_session.query(LeaveType).filter(LeaveType.code == "COMPENSATORY_OFF").first()
    adj = adjust_leave_balance(LeaveAdjustmentRequest(
        employee_id=staff.id,
        leave_type_id=comp_off_type.id,
        adjustment_days=2.0,
        remarks="Worked on Sunday production release"
    ), admin.id, db_session)

    assert adj.transaction_type == "MANUAL_ADJUSTMENT"
    assert adj.days == 2.0

    bal = get_employee_balance(staff.id, db_session)
    comp_detail = next(t for t in bal.type_balances if t.leave_type_code == "COMPENSATORY_OFF")
    assert comp_detail.manual_adjustments == 2.0
    assert comp_detail.available == 2.0

    # 2. Prevent self-approval: Admin submits leave for themselves, and tries to approve it
    admin_leave = apply_leave(admin_emp.id, LeaveCreate(
        leave_type="Casual Leave",
        start_date=date.today() + timedelta(days=60),
        end_date=date.today() + timedelta(days=60),
        reason="Personal day"
    ), db_session)

    with pytest.raises(HTTPException) as exc:
        review_leave(admin_leave.id, LeaveDecision(status="APPROVED"), admin.id, db_session)
    assert exc.value.status_code == 403
    assert "Employees cannot approve their own leave" in str(exc.value.detail)
