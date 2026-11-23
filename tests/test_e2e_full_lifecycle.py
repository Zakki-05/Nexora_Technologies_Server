"""
Comprehensive end-to-end integration test validating the entire WorkPulse EMS corporate lifecycle:
1. User registration & Employee Profile auto-provisioning
2. Multi-session punches & break management
3. Leave ledger, half-day leaves, approvals & cancellation refunds
4. Indian statutory payroll run & ReportLab PDF payslip generation
5. Announcements, notifications, audit logging & report exports
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
import pytest

from app.models.user import User
from app.models.department import Department
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.attendance_session import AttendanceSession
from app.models.break_session import BreakSession
from app.models.leave import Leave
from app.models.leave_type import LeaveType
from app.models.leave_transaction import LeaveTransaction
from app.models.salary import Salary
from app.models.salary_structure import SalaryStructure
from app.models.announcement import Announcement
from app.models.notification import Notification
from app.models.audit_log import AuditLog

from app.services.employee_service import ensure_employee_profile
from app.services import attendance_service, break_service, leave_service, salary_service
from app.services.announcement_service import create_announcement
from app.services.notification_service import create_notification, mark_all_as_read
from app.services.audit_service import log_audit
from app.services.report_service import generate_attendance_report, export_to_csv

from app.schemas.leave import LeaveCreate, LeaveDecision
from app.schemas.salary import PayrollRunRequest, SalaryStructureUpdate
from app.schemas.announcement import AnnouncementCreate
from app.utils.security import hash_password

def test_full_enterprise_workpulse_lifecycle(db_session):
    # -------------------------------------------------------------
    # Step 1: User Registration & Employee Profile Provisioning
    # -------------------------------------------------------------
    dept = Department(name="Engineering", description="Core software team")
    db_session.add(dept)
    db_session.commit()

    user = User(
        username="rahul_sharma",
        email="rahul.sharma@workpulse.com",
        hashed_password=hash_password("HashedSecret123!"),
        role="EMPLOYEE",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    emp = ensure_employee_profile(user, db_session)
    assert emp is not None
    assert emp.employee_code.startswith("EMP")
    assert emp.full_name == "Rahul Sharma"

    # Verify corporate leave ledger initialized with 10 corporate leave types
    balances = leave_service.get_employee_balance(emp.id, db_session)
    assert len(balances.type_balances) >= 10
    annual_bal = next((b for b in balances.type_balances if b.leave_type_code == "ANNUAL_LEAVE"), None)
    assert annual_bal is not None
    assert annual_bal.available > 0

    # -------------------------------------------------------------
    # Step 2: Multi-Session Attendance & Corporate Breaks
    # -------------------------------------------------------------
    # Session 1: Check in
    att1 = attendance_service.check_in(emp.id, db_session)
    assert att1 is not None
    assert att1.date == date.today()

    # Verify live status
    live_st = attendance_service.get_live_status(emp.id, db_session)
    assert live_st.is_punched_in is True
    assert live_st.active_session_number == 1

    # Start & End Tea Break (Paid)
    b_session = break_service.start_break(
        employee_id=emp.id,
        break_type="TEA_BREAK",
        remarks="Quick tea break",
        db=db_session
    )
    assert b_session.break_type == "TEA_BREAK"
    assert b_session.is_paid is True

    b_ended = break_service.end_break(
        employee_id=emp.id,
        db=db_session
    )
    assert b_ended.duration_minutes >= 1

    # Check out Session 1
    att1_out = attendance_service.check_out(emp.id, db_session)
    assert len(att1_out.sessions) == 1

    # Session 2: Check in again on the SAME day (Multi-session check-in)
    att2 = attendance_service.check_in(emp.id, db_session)
    assert att2.id == att1.id
    assert len(att2.sessions) == 2

    # Check out Session 2
    att2_out = attendance_service.check_out(emp.id, db_session)
    assert len(att2_out.sessions) == 2

    # Verify Daily Timeline
    timeline = attendance_service.get_daily_timeline(emp.id, date.today(), db_session)
    assert timeline.date == date.today()
    assert len(timeline.events) >= 4  # In, Break Start, Break End, Out...

    # -------------------------------------------------------------
    # Step 3: Corporate Leave Management & Transaction Ledger
    # -------------------------------------------------------------
    initial_avail = annual_bal.available
    future_start = date.today() + timedelta(days=20)
    leave_req = leave_service.apply_leave(
        emp.id,
        LeaveCreate(
            leave_type="ANNUAL_LEAVE",
            start_date=future_start,
            end_date=future_start,
            reason="Personal family commitment",
            is_half_day=True,
            half_day_session="FIRST_HALF"
        ),
        db_session
    )
    assert leave_req.days_count == 0.5
    assert leave_req.status == "PENDING"
    assert leave_req.is_half_day is True

    # Verify pending quota reserved
    bal_after_apply = leave_service.get_employee_balance(emp.id, db_session)
    ann_after_apply = next(b for b in bal_after_apply.type_balances if b.leave_type_code == "ANNUAL_LEAVE")
    assert ann_after_apply.pending_reserved == 0.5
    assert ann_after_apply.available == initial_avail - 0.5

    # Cancel Leave Application & Verify Refund to Ledger
    cancelled_leave = leave_service.cancel_leave(leave_req.id, emp.id, db_session)
    assert cancelled_leave.status == "CANCELLED"

    bal_after_cancel = leave_service.get_employee_balance(emp.id, db_session)
    ann_after_cancel = next(b for b in bal_after_cancel.type_balances if b.leave_type_code == "ANNUAL_LEAVE")
    assert ann_after_cancel.pending_reserved == 0.0
    assert ann_after_cancel.available == initial_avail

    # Inspect Ledger entries
    ledger = leave_service.get_leave_ledger(emp.id, db_session)
    assert len(ledger.items) >= 2  # Reservation + Refund

    # -------------------------------------------------------------
    # Step 4: Indian Statutory Payroll & PDF Payslips
    # -------------------------------------------------------------
    # Configure Employee CTC Structure
    struct_update = SalaryStructureUpdate(
        basic_salary=Decimal("30000.00"),
        hra=Decimal("12000.00"),
        conveyance=Decimal("1600.00"),
        medical_allowance=Decimal("1250.00"),
        special_allowance=Decimal("5150.00"),
        pf_deduction_rate=Decimal("12.00"),
        professional_tax=Decimal("200.00"),
        esi_rate=Decimal("0.00"),
        tds_rate=Decimal("5.00")
    )
    updated_struct = salary_service.update_salary_structure(emp.id, struct_update, db_session)
    assert updated_struct.basic_salary == Decimal("30000.00")
    assert updated_struct.gross_monthly == Decimal("56000.00")

    # Run Monthly Payroll Engine (PREVIEW)
    prev_payroll = salary_service.run_monthly_payroll(
        PayrollRunRequest(year=2026, month=11, action="PREVIEW"),
        db_session
    )
    assert prev_payroll.total_employees >= 1
    assert prev_payroll.total_net_payout > 0

    # Run Monthly Payroll Engine (PROCESS)
    proc_payroll = salary_service.run_monthly_payroll(
        PayrollRunRequest(year=2026, month=11, action="PROCESS"),
        db_session
    )
    assert proc_payroll.total_employees >= 1
    assert len(proc_payroll.items) >= 1

    # Retrieve generated salary record
    salary_record = db_session.query(Salary).filter(
        Salary.employee_id == emp.id,
        Salary.year == 2026,
        Salary.month == 11
    ).first()
    assert salary_record is not None
    assert salary_record.net_salary > Decimal("30000.00")

    # Generate Official ReportLab PDF Payslip
    pdf_bytes, filename = salary_service.get_payslip_pdf(salary_record.id, db_session)
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF")
    assert filename.endswith(".pdf")

    # -------------------------------------------------------------
    # Step 5: Enterprise Modules (Announcements, Notifications, Audit, Reports)
    # -------------------------------------------------------------
    # Announcement
    announcement = create_announcement(
        data=AnnouncementCreate(
            title="Annual Strategy Townhall 2026",
            message="All team members are requested to attend the Q4 Townhall meeting.",
            priority="HIGH",
            target_audience="ALL"
        ),
        author_user_id=user.id,
        db=db_session
    )
    assert announcement.id is not None
    assert announcement.priority == "HIGH"

    # Notification
    notif = create_notification(
        user_id=user.id,
        title="Payslip Published",
        message="Your November 2026 payslip has been generated.",
        type_str="PAYROLL",
        db=db_session
    )
    assert notif.id is not None
    assert notif.is_read is False

    # Mark as read
    marked_count = mark_all_as_read(user.id, db_session)
    assert marked_count >= 1

    # Audit Trail
    audit_log = log_audit(
        db=db_session,
        user_id=user.id,
        action="VERIFY_LIFECYCLE",
        resource_type="WORKPULSE_SYSTEM",
        resource_id="EMS-2026",
        ip_address="127.0.0.1"
    )
    assert audit_log is not None

    # Export Reports
    headers, rows, summary = generate_attendance_report(
        db=db_session,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 30)
    )
    assert len(headers) > 0
    csv_str = export_to_csv(headers, rows)
    assert len(csv_str) > 0
