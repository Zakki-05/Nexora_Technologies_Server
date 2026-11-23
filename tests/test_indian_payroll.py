from datetime import date, timedelta
from decimal import Decimal
import calendar
import pytest
from fastapi import HTTPException

from app.models.user import User
from app.models.department import Department
from app.models.employee import Employee
from app.models.leave import Leave
from app.models.attendance import Attendance
from app.models.salary import Salary
from app.models.salary_structure import SalaryStructure
from app.schemas.salary import (
    SalaryCreate,
    SalaryStructureUpdate,
    SalaryStructurePreviewRequest,
    PayrollRunRequest
)
from app.services.salary_service import (
    ensure_salary_structure,
    get_salary_structure,
    update_salary_structure,
    preview_salary_structure,
    compute_employee_payroll,
    calculate_lop_days,
    run_monthly_payroll,
    get_payslip_pdf,
    create_salary_record
)
from app.utils.security import hash_password
from app.utils.currency import amount_to_indian_words, format_inr

@pytest.fixture
def payroll_fixture(db_session):
    admin_user = User(
        username="hr_lead",
        email="hr_lead@ems.com",
        hashed_password=hash_password("HrLead123!"),
        role="ADMIN",
        is_active=True
    )
    emp_user1 = User(
        username="dev_anita",
        email="anita@ems.com",
        hashed_password=hash_password("AnitaPass123!"),
        role="EMPLOYEE",
        is_active=True
    )
    emp_user2 = User(
        username="intern_raj",
        email="raj@ems.com",
        hashed_password=hash_password("RajPass123!"),
        role="EMPLOYEE",
        is_active=True
    )
    dept = Department(name="Engineering", description="Software engineering")
    db_session.add_all([admin_user, emp_user1, emp_user2, dept])
    db_session.commit()

    emp1 = Employee(
        user_id=emp_user1.id,
        department_id=dept.id,
        employee_code="EMP-7001",
        full_name="Anita Desai",
        phone="+919876543210",
        hire_date=date(2025, 1, 15),
        position="Senior Backend Engineer",
        salary=Decimal("60000.00"),
        employment_status="ACTIVE"
    )
    # Low salary employee for ESI test (< 21000)
    emp2 = Employee(
        user_id=emp_user2.id,
        department_id=dept.id,
        employee_code="EMP-7002",
        full_name="Rajesh Kumar",
        phone="+919876543211",
        hire_date=date(2026, 2, 1),
        position="Engineering Intern",
        salary=Decimal("18000.00"),
        employment_status="ACTIVE"
    )
    db_session.add_all([emp1, emp2])
    db_session.commit()
    db_session.refresh(emp1)
    db_session.refresh(emp2)

    return {
        "admin": admin_user,
        "emp1": emp1,
        "emp2": emp2,
        "dept": dept
    }

# ==================== TEST CASES ====================

def test_salary_structure_auto_provision_and_preview(db_session, payroll_fixture):
    emp1 = payroll_fixture["emp1"]

    # 1. Auto-provision check
    struct = get_salary_structure(emp1.id, db_session)
    assert struct.employee_id == emp1.id
    # 50% of 60,000 is 30,000
    assert struct.basic_salary == Decimal("30000.00")
    # 40% of Basic is 12,000
    assert struct.hra == Decimal("12000.00")
    assert struct.conveyance == Decimal("1600.00")
    assert struct.medical_allowance == Decimal("1250.00")
    # Special allowance is the remainder (60,000 - 30,000 - 12,000 - 1,600 - 1,250 = 15,150)
    assert struct.special_allowance == Decimal("15150.00")
    assert struct.gross_monthly == Decimal("60000.00")
    assert struct.pf_deduction_rate == Decimal("12.00")
    assert struct.professional_tax == Decimal("200.00")

    # 2. Update structure
    updated = update_salary_structure(emp1.id, SalaryStructureUpdate(
        special_allowance=Decimal("16000.00"),
        professional_tax=Decimal("200.00")
    ), db_session)
    assert updated.special_allowance == Decimal("16000.00")
    assert updated.gross_monthly == Decimal("60850.00")

    # 3. Preview annual CTC simulation
    preview = preview_salary_structure(SalaryStructurePreviewRequest(
        annual_ctc=Decimal("600000.00"),  # 50,000/mo
        basic_percentage=Decimal("50.00"),
        hra_percentage=Decimal("40.00")
    ))
    assert preview.monthly_ctc == Decimal("50000.00")
    assert preview.basic_salary == Decimal("25000.00")
    assert preview.hra == Decimal("10000.00")
    assert preview.pf_monthly == Decimal("3000.00")  # 12% of 25000
    assert preview.professional_tax == Decimal("200.00")
    assert preview.total_deductions == Decimal("3200.00")
    assert preview.net_take_home == Decimal("46800.00")

def test_statutory_deductions_high_vs_low_earner(db_session, payroll_fixture):
    emp1 = payroll_fixture["emp1"]
    emp2 = payroll_fixture["emp2"]

    # High earner (Anita: Gross 60,000)
    p1 = compute_employee_payroll(emp1.id, year=2026, month=11, db=db_session)
    assert p1["basic_salary"] == Decimal("30000.00")
    assert p1["gross_earnings"] == Decimal("60000.00")
    assert p1["pf_deduction"] == Decimal("3600.00")  # 12% of 30,000
    assert p1["professional_tax"] == Decimal("200.00")
    # Gross > 21,000 -> ESIC is 0
    assert p1["esi_deduction"] == Decimal("0.00")
    assert p1["deductions"] == Decimal("3800.00")  # 3600 + 200
    assert p1["net_salary"] == Decimal("56200.00")  # 60,000 - 3,800

    # Low earner (Raj: Gross 18,000 <= 21,000 threshold)
    p2 = compute_employee_payroll(emp2.id, year=2026, month=11, db=db_session)
    assert p2["gross_earnings"] == Decimal("18000.00")
    assert p2["pf_deduction"] == Decimal("1080.00")  # 12% of 9,000
    assert p2["professional_tax"] == Decimal("200.00")
    # ESIC = 0.75% of 18,000 = 135.00
    assert p2["esi_deduction"] == Decimal("135.00")
    assert p2["deductions"] == Decimal("1415.00")  # 1080 + 200 + 135
    assert p2["net_salary"] == Decimal("16585.00")  # 18,000 - 1,415

def test_attendance_and_unpaid_leave_lop_integration(db_session, payroll_fixture):
    emp1 = payroll_fixture["emp1"]

    # November 2026 has 30 days
    # Record 2 days of approved Unpaid Leave
    unpaid_leave = Leave(
        employee_id=emp1.id,
        leave_type="UNPAID_LEAVE",
        start_date=date(2026, 11, 4),
        end_date=date(2026, 11, 5),  # 2 days
        days_count=2.0,
        status="APPROVED"
    )
    # Record 1 day of ABSENT attendance
    absent_day = Attendance(
        employee_id=emp1.id,
        date=date(2026, 11, 10),
        status="ABSENT"
    )
    db_session.add_all([unpaid_leave, absent_day])
    db_session.commit()

    lop_days, days_in_month = calculate_lop_days(emp1.id, year=2026, month=11, db=db_session)
    assert lop_days == Decimal("3.0")
    assert days_in_month == 30

    p = compute_employee_payroll(emp1.id, year=2026, month=11, db=db_session)
    # Gross is 60,000. Per-day gross = 60,000 / 30 = 2,000.00
    # LOP = 2,000 * 3 = 6,000.00
    assert p["loss_of_pay"] == Decimal("6000.00")
    assert p["lop_days"] == Decimal("3.0")
    # Total deductions: 3600 (PF) + 200 (PT) + 6000 (LOP) = 9800.00
    assert p["deductions"] == Decimal("9800.00")
    # Net salary: 60,000 - 9,800 = 50,200.00
    assert p["net_salary"] == Decimal("50200.00")

def test_monthly_payroll_run_preview_process_lock(db_session, payroll_fixture):
    payroll_fixture["emp1"]
    payroll_fixture["emp2"]

    # 1. PREVIEW: Does not write to DB
    prev_res = run_monthly_payroll(PayrollRunRequest(
        month=11,
        year=2026,
        action="PREVIEW"
    ), db_session)
    assert prev_res.action == "PREVIEW"
    assert prev_res.total_employees == 2
    # Verify no records saved
    count_before = db_session.query(Salary).filter(Salary.month == 11, Salary.year == 2026).count()
    assert count_before == 0

    # 2. PROCESS: Saves records
    proc_res = run_monthly_payroll(PayrollRunRequest(
        month=11,
        year=2026,
        action="PROCESS"
    ), db_session)
    assert proc_res.action == "PROCESS"
    assert proc_res.total_employees == 2
    count_after = db_session.query(Salary).filter(Salary.month == 11, Salary.year == 2026).count()
    assert count_after == 2

    # Check un-locked initially
    salaries = db_session.query(Salary).filter(Salary.month == 11, Salary.year == 2026).all()
    assert all(not s.is_locked for s in salaries)

    # 3. LOCK: Locks records
    lock_res = run_monthly_payroll(PayrollRunRequest(
        month=11,
        year=2026,
        action="LOCK"
    ), db_session)
    assert lock_res.action == "LOCK"

    salaries_locked = db_session.query(Salary).filter(Salary.month == 11, Salary.year == 2026).all()
    assert all(s.is_locked for s in salaries_locked)

    # 4. Attempting to re-process while locked fails with 409 Conflict
    with pytest.raises(HTTPException) as exc:
        run_monthly_payroll(PayrollRunRequest(
            month=11,
            year=2026,
            action="PROCESS"
        ), db_session)
    assert exc.value.status_code == 409
    assert "already locked" in str(exc.value.detail)

def test_duplicate_salary_prevention(db_session, payroll_fixture):
    emp1 = payroll_fixture["emp1"]

    create_salary_record(SalaryCreate(
        employee_id=emp1.id,
        month=12,
        year=2026,
        basic_salary=Decimal("40000.00"),
        allowances=Decimal("5000.00"),
        deductions=Decimal("3000.00"),
        payment_date=date(2026, 12, 31)
    ), db_session)

    # Duplicate creation fails
    with pytest.raises(HTTPException) as exc:
        create_salary_record(SalaryCreate(
            employee_id=emp1.id,
            month=12,
            year=2026,
            basic_salary=Decimal("40000.00"),
            allowances=Decimal("5000.00"),
            deductions=Decimal("3000.00"),
            payment_date=date(2026, 12, 31)
        ), db_session)
    assert exc.value.status_code == 409

def test_pdf_payslip_generation(db_session, payroll_fixture):
    emp1 = payroll_fixture["emp1"]

    # Process salary
    sal = create_salary_record(SalaryCreate(
        employee_id=emp1.id,
        month=10,
        year=2026,
        basic_salary=Decimal("30000.00"),
        hra=Decimal("12000.00"),
        special_allowance=Decimal("18000.00"),
        pf_deduction=Decimal("3600.00"),
        professional_tax=Decimal("200.00"),
        payment_date=date(2026, 10, 31)
    ), db_session)

    pdf_bytes, filename = get_payslip_pdf(sal.id, db_session)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")
    assert filename.startswith("Payslip_EMP-7001_2026_10")

def test_indian_currency_formatting():
    assert format_inr(Decimal("56200.00")) == "₹56,200.00"
    assert format_inr(Decimal("1250450.75")) == "₹12,50,450.75"
    assert amount_to_indian_words(Decimal("56200.00")) == "Rupees Fifty Six Thousand Two Hundred Only"
