from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import calendar
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from fastapi import HTTPException, status

from app.models.salary import Salary
from app.models.salary_structure import SalaryStructure
from app.models.employee import Employee
from app.models.department import Department
from app.models.leave import Leave
from app.models.attendance import Attendance
from app.schemas.salary import (
    SalaryCreate,
    SalaryUpdate,
    SalaryResponse,
    SalarySummary,
    SalaryStructureCreate,
    SalaryStructureUpdate,
    SalaryStructureResponse,
    SalaryStructurePreviewRequest,
    SalaryStructurePreviewResponse,
    PayrollRunRequest,
    PayrollRunResponse,
    PayrollRunItem
)
from app.schemas.common import PaginatedResponse
from app.utils.pagination import paginate
from app.utils.payslip_pdf import generate_payslip_pdf

# ==================== HELPER & CALCULATION FUNCTIONS ====================

def round_inr(val: Decimal | float | int) -> Decimal:
    """Rounds monetary values to 2 decimal places using standard financial half-up rule."""
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def calculate_net_salary(basic: Decimal, allowances: Decimal, deductions: Decimal) -> Decimal:
    return max(Decimal("0.00"), round_inr(basic + allowances - deductions))

def ensure_salary_structure(employee_id: int, db: Session) -> SalaryStructure:
    """
    Retrieves or auto-provisions a compliant Indian salary structure for an employee
    based on standard 50% Basic, 40% HRA, Conveyance, Medical, and PF/PT statutory rates.
    """
    struct = db.query(SalaryStructure).filter(
        SalaryStructure.employee_id == employee_id,
        SalaryStructure.is_active == True
    ).first()

    if not struct:
        emp = db.query(Employee).filter(Employee.id == employee_id).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        total_salary = Decimal(str(emp.salary or "50000.00"))
        basic = round_inr(total_salary * Decimal("0.50"))
        hra = round_inr(basic * Decimal("0.40"))
        conveyance = Decimal("1600.00")
        medical = Decimal("1250.00")
        allocated = basic + hra + conveyance + medical
        special = max(Decimal("0.00"), total_salary - allocated)

        struct = SalaryStructure(
            employee_id=employee_id,
            basic_salary=basic,
            hra=hra,
            da=Decimal("0.00"),
            conveyance=conveyance,
            medical_allowance=medical,
            special_allowance=special,
            pf_deduction_rate=Decimal("12.00"),
            professional_tax=Decimal("200.00"),
            esi_rate=Decimal("0.75") if total_salary <= Decimal("21000.00") else Decimal("0.00"),
            tds_rate=Decimal("0.00"),
            is_active=True
        )
        db.add(struct)
        try:
            db.commit()
            db.refresh(struct)
        except Exception:
            db.rollback()
            struct = db.query(SalaryStructure).filter(SalaryStructure.employee_id == employee_id).first()

    return struct

def calculate_lop_days(employee_id: int, year: int, month: int, db: Session) -> Tuple[Decimal, int]:
    """
    Computes Loss of Pay (LOP) days in a given month from:
    1. Approved UNPAID_LEAVE / Loss of Pay leave applications.
    2. Unapproved ABSENT attendance records.
    """
    days_in_month = calendar.monthrange(year, month)[1]
    m_start = date(year, month, 1)
    m_end = date(year, month, days_in_month)

    # 1. Unpaid approved leaves overlapping this month
    unpaid_leaves = db.query(Leave).filter(
        Leave.employee_id == employee_id,
        Leave.status == "APPROVED",
        Leave.leave_type.in_(["Unpaid", "UNPAID_LEAVE", "Unpaid Leave", "Loss of Pay"]),
        Leave.start_date <= m_end,
        Leave.end_date >= m_start
    ).all()

    lop_leave_days = Decimal("0.0")
    for l in unpaid_leaves:
        # Overlapping slice in this month
        eff_start = max(l.start_date, m_start)
        eff_end = min(l.end_date, m_end)
        days = Decimal(str((eff_end - eff_start).days + 1))
        lop_leave_days += days

    # 2. Absent attendance records in this month
    absent_count = db.query(Attendance).filter(
        Attendance.employee_id == employee_id,
        Attendance.status == "ABSENT",
        Attendance.date >= m_start,
        Attendance.date <= m_end
    ).count()

    total_lop = round_inr(lop_leave_days + Decimal(str(absent_count)))
    return (total_lop, days_in_month)

def compute_employee_payroll(employee_id: int, year: int, month: int, db: Session) -> dict:
    """
    Computes complete statutory payroll metrics for an employee in INR:
    Gross = Basic + HRA + DA + Conveyance + Medical + Special Allowance
    Deductions = EPF (12% of Basic+DA) + PT + ESI + TDS + Loss of Pay (LOP)
    """
    emp = db.query(Employee).options(joinedload(Employee.department)).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    struct = ensure_salary_structure(employee_id, db)

    basic = Decimal(str(struct.basic_salary))
    hra = Decimal(str(struct.hra))
    da = Decimal(str(struct.da))
    conveyance = Decimal(str(struct.conveyance))
    medical = Decimal(str(struct.medical_allowance))
    special = Decimal(str(struct.special_allowance))

    gross_monthly = round_inr(basic + hra + da + conveyance + medical + special)

    # Loss of pay
    lop_days, days_in_month = calculate_lop_days(employee_id, year, month, db)
    per_day_rate = round_inr(gross_monthly / Decimal(str(days_in_month)))
    loss_of_pay = round_inr(per_day_rate * lop_days)

    # Statutory EPF (12% of Basic + DA)
    pf_base = basic + da
    pf_deduction = round_inr(pf_base * (struct.pf_deduction_rate / Decimal("100.00")))

    # Professional Tax
    professional_tax = round_inr(struct.professional_tax)

    # ESIC (0.75% of Gross if gross <= 21,000)
    esi_deduction = Decimal("0.00")
    if gross_monthly <= Decimal("21000.00") and struct.esi_rate > 0:
        esi_deduction = round_inr(gross_monthly * (struct.esi_rate / Decimal("100.00")))

    # TDS / Income Tax
    tds_deduction = round_inr(gross_monthly * (struct.tds_rate / Decimal("100.00")))

    total_allowances = hra + da + conveyance + medical + special
    total_deductions = round_inr(pf_deduction + professional_tax + esi_deduction + tds_deduction + loss_of_pay)
    net_salary = max(Decimal("0.00"), round_inr(gross_monthly - total_deductions))

    dept_name = emp.department.name if emp.department else "General"

    return {
        "employee_id": emp.id,
        "employee_code": emp.employee_code,
        "employee_name": emp.full_name,
        "department_name": dept_name,
        "basic_salary": basic,
        "hra": hra,
        "da": da,
        "conveyance": conveyance,
        "medical": medical,
        "special_allowance": special,
        "allowances": total_allowances,
        "gross_earnings": gross_monthly,
        "pf_deduction": pf_deduction,
        "professional_tax": professional_tax,
        "esi_deduction": esi_deduction,
        "tds_deduction": tds_deduction,
        "loss_of_pay": loss_of_pay,
        "lop_days": lop_days,
        "deductions": total_deductions,
        "net_salary": net_salary
    }

def format_salary_response(salary: Salary) -> SalaryResponse:
    """Formats a Salary model into SalaryResponse with calculated gross earnings."""
    basic = Decimal(str(salary.basic_salary or "0.00"))
    allowances = Decimal(str(salary.allowances or "0.00"))
    hra = Decimal(str(salary.hra or "0.00"))
    da = Decimal(str(salary.da or "0.00"))
    conveyance = Decimal(str(salary.conveyance or "0.00"))
    medical = Decimal(str(salary.medical or "0.00"))
    special = Decimal(str(salary.special_allowance or "0.00"))
    bonus = Decimal(str(salary.bonus or "0.00"))
    ot = Decimal(str(salary.overtime_pay or "0.00"))

    # If specific components are provided, calculate detailed gross; else fallback to basic + allowances
    detailed_components = hra + da + conveyance + medical + special + bonus + ot
    gross = basic + (detailed_components if detailed_components > 0 else allowances)

    return SalaryResponse(
        id=salary.id,
        employee_id=salary.employee_id,
        month=salary.month,
        year=salary.year,
        basic_salary=basic,
        hra=hra,
        da=da,
        conveyance=conveyance,
        medical=medical,
        special_allowance=special,
        bonus=bonus,
        overtime_pay=ot,
        allowances=allowances,
        gross_earnings=round_inr(gross),
        pf_deduction=Decimal(str(salary.pf_deduction or "0.00")),
        professional_tax=Decimal(str(salary.professional_tax or "0.00")),
        tds_deduction=Decimal(str(salary.tds_deduction or "0.00")),
        esi_deduction=Decimal(str(salary.esi_deduction or "0.00")),
        loss_of_pay=Decimal(str(salary.loss_of_pay or "0.00")),
        lop_days=Decimal(str(salary.lop_days or "0.0")),
        deductions=Decimal(str(salary.deductions or "0.00")),
        net_salary=Decimal(str(salary.net_salary or "0.00")),
        payment_date=salary.payment_date,
        status=salary.status,
        payment_method=salary.payment_method,
        is_locked=bool(salary.is_locked),
        notes=salary.notes,
        created_at=salary.created_at,
        employee=salary.employee
    )

# ==================== SALARY STRUCTURE SERVICES ====================

def get_all_salary_structures(
    db: Session,
    page: int = 1,
    size: int = 20
) -> PaginatedResponse[SalaryStructureResponse]:
    query = db.query(SalaryStructure).options(
        joinedload(SalaryStructure.employee)
    ).order_by(SalaryStructure.id.asc())

    paginated = paginate(query, page, size)
    items: List[SalaryStructureResponse] = []
    for s in paginated.items:
        gross = (
            s.basic_salary + s.hra + s.da +
            s.conveyance + s.medical_allowance + s.special_allowance
        )
        emp_name = s.employee.full_name if s.employee else None
        emp_code = s.employee.employee_code if s.employee else None
        items.append(SalaryStructureResponse(
            id=s.id,
            employee_id=s.employee_id,
            basic_salary=s.basic_salary,
            hra=s.hra,
            da=s.da,
            conveyance=s.conveyance,
            medical_allowance=s.medical_allowance,
            special_allowance=s.special_allowance,
            gross_monthly=round_inr(gross),
            pf_deduction_rate=s.pf_deduction_rate,
            professional_tax=s.professional_tax,
            esi_rate=s.esi_rate,
            tds_rate=s.tds_rate,
            is_active=s.is_active,
            employee_name=emp_name,
            employee_code=emp_code,
            created_at=s.created_at,
            updated_at=s.updated_at
        ))

    return PaginatedResponse[SalaryStructureResponse](
        items=items,
        total=paginated.total,
        page=paginated.page,
        size=paginated.size,
        pages=paginated.pages
    )

def get_salary_structure(employee_id: int, db: Session) -> SalaryStructureResponse:
    s = ensure_salary_structure(employee_id, db)
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    gross = s.basic_salary + s.hra + s.da + s.conveyance + s.medical_allowance + s.special_allowance
    return SalaryStructureResponse(
        id=s.id,
        employee_id=s.employee_id,
        basic_salary=s.basic_salary,
        hra=s.hra,
        da=s.da,
        conveyance=s.conveyance,
        medical_allowance=s.medical_allowance,
        special_allowance=s.special_allowance,
        gross_monthly=round_inr(gross),
        pf_deduction_rate=s.pf_deduction_rate,
        professional_tax=s.professional_tax,
        esi_rate=s.esi_rate,
        tds_rate=s.tds_rate,
        is_active=s.is_active,
        employee_name=emp.full_name if emp else None,
        employee_code=emp.employee_code if emp else None,
        created_at=s.created_at,
        updated_at=s.updated_at
    )

def update_salary_structure(
    employee_id: int,
    data: SalaryStructureUpdate,
    db: Session
) -> SalaryStructureResponse:
    s = ensure_salary_structure(employee_id, db)
    update_data = data.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(s, key, value)

    try:
        db.commit()
        db.refresh(s)
        return get_salary_structure(employee_id, db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update salary structure: {str(exc)}"
        )

def preview_salary_structure(data: SalaryStructurePreviewRequest) -> SalaryStructurePreviewResponse:
    """Calculates an accurate Indian salary breakdown preview from annual CTC."""
    annual_ctc = round_inr(data.annual_ctc)
    monthly_ctc = round_inr(annual_ctc / Decimal("12.00"))

    basic = round_inr(monthly_ctc * (data.basic_percentage / Decimal("100.00")))
    hra = round_inr(basic * (data.hra_percentage / Decimal("100.00")))
    conveyance = data.conveyance_monthly
    medical = data.medical_monthly
    da = Decimal("0.00")

    allocated = basic + hra + da + conveyance + medical
    special = max(Decimal("0.00"), monthly_ctc - allocated)

    gross_monthly = basic + hra + da + conveyance + medical + special

    # Deductions
    pf = round_inr((basic + da) * (data.pf_deduction_rate / Decimal("100.00")))
    pt = data.professional_tax
    esi = Decimal("0.00")
    if gross_monthly <= Decimal("21000.00") and data.esi_rate > 0:
        esi = round_inr(gross_monthly * (data.esi_rate / Decimal("100.00")))
    tds = round_inr(gross_monthly * (data.tds_rate / Decimal("100.00")))

    total_deductions = pf + pt + esi + tds
    net_take_home = max(Decimal("0.00"), gross_monthly - total_deductions)

    return SalaryStructurePreviewResponse(
        annual_ctc=annual_ctc,
        monthly_ctc=monthly_ctc,
        basic_salary=basic,
        hra=hra,
        da=da,
        conveyance=conveyance,
        medical_allowance=medical,
        special_allowance=special,
        gross_monthly=gross_monthly,
        pf_monthly=pf,
        professional_tax=pt,
        esi_monthly=esi,
        tds_monthly=tds,
        total_deductions=total_deductions,
        net_take_home=net_take_home
    )

# ==================== MONTHLY PAYROLL RUN ENGINE ====================

def run_monthly_payroll(data: PayrollRunRequest, db: Session) -> PayrollRunResponse:
    """
    Organization-wide monthly payroll run engine:
    Supports PREVIEW (simulation), PROCESS (generate records), and LOCK (lock payroll).
    """
    month = data.month
    year = data.year
    action = data.action.upper()
    payment_date = data.payment_date or date(year, month, calendar.monthrange(year, month)[1])

    # 1. Action: LOCK
    if action == "LOCK":
        salaries = db.query(Salary).filter(
            Salary.month == month,
            Salary.year == year
        ).all()
        if not salaries:
            raise HTTPException(
                status_code=404,
                detail=f"No payroll records found for {month}/{year} to lock"
            )
        for s in salaries:
            s.is_locked = True
        db.commit()

        total_gross = sum((Decimal(str(s.basic_salary + s.allowances)) for s in salaries), Decimal("0.00"))
        total_ded = sum((Decimal(str(s.deductions)) for s in salaries), Decimal("0.00"))
        total_net = sum((Decimal(str(s.net_salary)) for s in salaries), Decimal("0.00"))

        return PayrollRunResponse(
            month=month,
            year=year,
            action="LOCK",
            total_employees=len(salaries),
            total_gross=round_inr(total_gross),
            total_deductions=round_inr(total_ded),
            total_net_payout=round_inr(total_net),
            items=[],
            message=f"Payroll for {month}/{year} successfully locked ({len(salaries)} records)."
        )

    # 2. Query target employees
    emp_query = db.query(Employee).filter(Employee.employment_status == "ACTIVE")
    if data.department_id:
        emp_query = emp_query.filter(Employee.department_id == data.department_id)
    if data.employee_id:
        emp_query = emp_query.filter(Employee.id == data.employee_id)

    target_employees = emp_query.all()
    if not target_employees:
        raise HTTPException(status_code=404, detail="No active employees found matching criteria")

    run_items: List[PayrollRunItem] = []
    tot_gross = Decimal("0.00")
    tot_ded = Decimal("0.00")
    tot_net = Decimal("0.00")

    # Check for existing locked records in process mode
    if action == "PROCESS":
        existing_locked = db.query(Salary).filter(
            Salary.month == month,
            Salary.year == year,
            Salary.is_locked == True,
            Salary.employee_id.in_([e.id for e in target_employees])
        ).first()
        if existing_locked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Payroll for {month}/{year} is already locked. Modify or unlock first."
            )

    for emp in target_employees:
        metrics = compute_employee_payroll(emp.id, year, month, db)
        tot_gross += metrics["gross_earnings"]
        tot_ded += metrics["deductions"]
        tot_net += metrics["net_salary"]

        is_locked_val = False
        status_val = "PAID"

        if action == "PROCESS":
            # Upsert into Salary table
            record = db.query(Salary).filter(
                Salary.employee_id == emp.id,
                Salary.month == month,
                Salary.year == year
            ).first()

            if not record:
                record = Salary(
                    employee_id=emp.id,
                    month=month,
                    year=year,
                    basic_salary=metrics["basic_salary"],
                    hra=metrics["hra"],
                    da=metrics["da"],
                    conveyance=metrics["conveyance"],
                    medical=metrics["medical"],
                    special_allowance=metrics["special_allowance"],
                    bonus=Decimal("0.00"),
                    overtime_pay=Decimal("0.00"),
                    allowances=metrics["allowances"],
                    pf_deduction=metrics["pf_deduction"],
                    professional_tax=metrics["professional_tax"],
                    esi_deduction=metrics["esi_deduction"],
                    tds_deduction=metrics["tds_deduction"],
                    loss_of_pay=metrics["loss_of_pay"],
                    lop_days=metrics["lop_days"],
                    deductions=metrics["deductions"],
                    net_salary=metrics["net_salary"],
                    payment_date=payment_date,
                    status="PAID",
                    payment_method=data.payment_method,
                    is_locked=False,
                    notes=f"Processed payroll for {month}/{year}"
                )
                db.add(record)
            else:
                record.basic_salary = metrics["basic_salary"]
                record.hra = metrics["hra"]
                record.da = metrics["da"]
                record.conveyance = metrics["conveyance"]
                record.medical = metrics["medical"]
                record.special_allowance = metrics["special_allowance"]
                record.allowances = metrics["allowances"]
                record.pf_deduction = metrics["pf_deduction"]
                record.professional_tax = metrics["professional_tax"]
                record.esi_deduction = metrics["esi_deduction"]
                record.tds_deduction = metrics["tds_deduction"]
                record.loss_of_pay = metrics["loss_of_pay"]
                record.lop_days = metrics["lop_days"]
                record.deductions = metrics["deductions"]
                record.net_salary = metrics["net_salary"]
                record.payment_date = payment_date
                record.payment_method = data.payment_method

            is_locked_val = record.is_locked
            status_val = record.status

        run_items.append(PayrollRunItem(
            employee_id=emp.id,
            employee_code=metrics["employee_code"],
            employee_name=metrics["employee_name"],
            department_name=metrics["department_name"],
            basic_salary=metrics["basic_salary"],
            gross_earnings=metrics["gross_earnings"],
            pf_deduction=metrics["pf_deduction"],
            professional_tax=metrics["professional_tax"],
            esi_deduction=metrics["esi_deduction"],
            tds_deduction=metrics["tds_deduction"],
            lop_days=metrics["lop_days"],
            loss_of_pay=metrics["loss_of_pay"],
            total_deductions=metrics["deductions"],
            net_salary=metrics["net_salary"],
            status=status_val,
            is_locked=is_locked_val
        ))

    if action == "PROCESS":
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to process payroll: {str(exc)}"
            )

    msg = (
        f"Payroll preview generated for {len(run_items)} employees."
        if action == "PREVIEW"
        else f"Payroll successfully generated and processed for {len(run_items)} employees."
    )

    return PayrollRunResponse(
        month=month,
        year=year,
        action=action,
        total_employees=len(run_items),
        total_gross=round_inr(tot_gross),
        total_deductions=round_inr(tot_ded),
        total_net_payout=round_inr(tot_net),
        items=run_items,
        message=msg
    )

# ==================== PDF PAYSLIP GENERATION ====================

def get_payslip_pdf(salary_id: int, db: Session) -> Tuple[bytes, str]:
    """Generates high-resolution PDF payslip bytes and an official filename."""
    salary = db.query(Salary).options(
        joinedload(Salary.employee).joinedload(Employee.department)
    ).filter(Salary.id == salary_id).first()

    if not salary:
        raise HTTPException(status_code=404, detail="Salary record not found")

    emp = salary.employee
    dept_name = emp.department.name if emp and emp.department else "General"
    pdf_bytes = generate_payslip_pdf(salary, emp, department_name=dept_name)

    emp_code = emp.employee_code if emp else f"EMP-{salary.employee_id}"
    month_int = salary.month or salary.payment_date.month
    year_int = salary.year or salary.payment_date.year
    filename = f"Payslip_{emp_code}_{year_int}_{month_int:02d}.pdf"

    return (pdf_bytes, filename)

# ==================== CORE SALARY RECORD CRUD (BACKWARD COMPATIBLE) ====================

def create_salary_record(data: SalaryCreate, db: Session) -> Salary:
    employee = db.query(Employee).filter(Employee.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    month = data.month or data.payment_date.month
    year = data.year or data.payment_date.year

    # Check duplicate prevention
    existing = db.query(Salary).filter(
        Salary.employee_id == data.employee_id,
        Salary.month == month,
        Salary.year == year
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A salary record already exists for employee #{data.employee_id} for period {month}/{year}"
        )

    detailed_allowances = data.hra + data.da + data.conveyance + data.medical + data.special_allowance + data.bonus + data.overtime_pay
    total_allowances = detailed_allowances if detailed_allowances > 0 else data.allowances

    detailed_deductions = data.pf_deduction + data.professional_tax + data.esi_deduction + data.tds_deduction + data.loss_of_pay
    total_deductions = detailed_deductions if detailed_deductions > 0 else data.deductions

    net = calculate_net_salary(data.basic_salary, total_allowances, total_deductions)

    try:
        salary = Salary(
            employee_id=data.employee_id,
            month=month,
            year=year,
            basic_salary=data.basic_salary,
            hra=data.hra,
            da=data.da,
            conveyance=data.conveyance,
            medical=data.medical,
            special_allowance=data.special_allowance,
            bonus=data.bonus,
            overtime_pay=data.overtime_pay,
            allowances=total_allowances,
            pf_deduction=data.pf_deduction,
            professional_tax=data.professional_tax,
            tds_deduction=data.tds_deduction,
            esi_deduction=data.esi_deduction,
            loss_of_pay=data.loss_of_pay,
            lop_days=data.lop_days,
            deductions=total_deductions,
            net_salary=net,
            payment_date=data.payment_date,
            status=data.status,
            payment_method=data.payment_method,
            is_locked=False,
            notes=data.notes
        )
        db.add(salary)
        db.commit()
        db.refresh(salary)
        return salary
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create salary record: {str(exc)}"
        )

def get_all_salaries(
    db: Session,
    page: int = 1,
    size: int = 20,
    employee_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None
) -> PaginatedResponse[SalaryResponse]:
    query = db.query(Salary).options(joinedload(Salary.employee))

    if employee_id:
        query = query.filter(Salary.employee_id == employee_id)
    if status_filter:
        query = query.filter(Salary.status == status_filter.upper())
    if year and isinstance(year, int):
        query = query.filter(
            (Salary.year == year) | (func.extract("year", Salary.payment_date) == year)
        )
    if month and isinstance(month, int):
        query = query.filter(
            (Salary.month == month) | (func.extract("month", Salary.payment_date) == month)
        )

    query = query.order_by(Salary.payment_date.desc(), Salary.id.desc())
    paginated = paginate(query, page, size)

    items = [format_salary_response(s) for s in paginated.items]
    return PaginatedResponse[SalaryResponse](
        items=items,
        total=paginated.total,
        page=paginated.page,
        size=paginated.size,
        pages=paginated.pages
    )

def get_employee_salaries(
    employee_id: int,
    db: Session,
    page: int = 1,
    size: int = 20
) -> PaginatedResponse[SalaryResponse]:
    query = db.query(Salary).options(joinedload(Salary.employee)).filter(
        Salary.employee_id == employee_id
    ).order_by(Salary.payment_date.desc(), Salary.id.desc())

    paginated = paginate(query, page, size)
    items = [format_salary_response(s) for s in paginated.items]
    return PaginatedResponse[SalaryResponse](
        items=items,
        total=paginated.total,
        page=paginated.page,
        size=paginated.size,
        pages=paginated.pages
    )

def get_salary_by_id(salary_id: int, db: Session) -> Salary:
    salary = db.query(Salary).options(joinedload(Salary.employee)).filter(
        Salary.id == salary_id
    ).first()
    if not salary:
        raise HTTPException(status_code=404, detail="Salary record not found")
    return salary

def update_salary(salary_id: int, data: SalaryUpdate, db: Session) -> Salary:
    salary = get_salary_by_id(salary_id, db)
    if salary.is_locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot update a locked salary record"
        )

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(salary, key, value)

    detailed_allowances = salary.hra + salary.da + salary.conveyance + salary.medical + salary.special_allowance + salary.bonus + salary.overtime_pay
    total_allowances = detailed_allowances if detailed_allowances > 0 else salary.allowances

    detailed_deductions = salary.pf_deduction + salary.professional_tax + salary.esi_deduction + salary.tds_deduction + salary.loss_of_pay
    total_deductions = detailed_deductions if detailed_deductions > 0 else salary.deductions

    salary.net_salary = calculate_net_salary(
        salary.basic_salary,
        total_allowances,
        total_deductions
    )

    try:
        db.commit()
        db.refresh(salary)
        return salary
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update salary: {str(exc)}"
        )

def get_salary_summary(
    db: Session,
    year: Optional[int] = None,
    month: Optional[int] = None
) -> SalarySummary:
    query = db.query(Salary)
    if year:
        query = query.filter((Salary.year == year) | (func.extract("year", Salary.payment_date) == year))
    if month:
        query = query.filter((Salary.month == month) | (func.extract("month", Salary.payment_date) == month))

    salaries = query.all()
    total_payroll = sum((s.net_salary for s in salaries), Decimal("0.00"))
    total_paid = sum((s.net_salary for s in salaries if s.status == "PAID"), Decimal("0.00"))
    total_pending = sum((s.net_salary for s in salaries if s.status == "PENDING"), Decimal("0.00"))

    return SalarySummary(
        total_payroll=round_inr(total_payroll),
        total_paid=round_inr(total_paid),
        total_pending=round_inr(total_pending),
        record_count=len(salaries)
    )

def delete_salary(salary_id: int, db: Session) -> dict:
    salary = get_salary_by_id(salary_id, db)
    if salary.is_locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a locked salary record"
        )
    try:
        db.delete(salary)
        db.commit()
        return {"message": "Salary record deleted successfully", "success": True}
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete salary: {str(exc)}"
        )
