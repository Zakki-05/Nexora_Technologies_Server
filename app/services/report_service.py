import io
import csv
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.models.employee import Employee
from app.models.department import Department
from app.models.attendance import Attendance
from app.models.leave import Leave
from app.models.salary import Salary
from app.utils.excel import create_xlsx

# 1. Employee Report
def generate_employee_report(
    db: Session,
    department_id: Optional[int] = None,
    employment_status: Optional[str] = None
) -> Tuple[List[str], List[List[Any]], Dict[str, Any]]:
    headers = [
        "Employee Code", "Full Name", "Email", "Phone",
        "Department", "Position", "Salary", "Status",
        "Hire Date", "Gender"
    ]
    query = db.query(Employee).options(
        joinedload(Employee.department),
        joinedload(Employee.user)
    )

    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if employment_status:
        query = query.filter(Employee.employment_status == employment_status.upper())

    employees = query.order_by(Employee.id.asc()).all()

    rows = []
    total_salary = Decimal("0.00")
    for emp in employees:
        email = emp.user.email if emp.user else "N/A"
        dept_name = emp.department.name if emp.department else "N/A"
        total_salary += emp.salary
        rows.append([
            emp.employee_code,
            emp.full_name,
            email,
            emp.phone,
            dept_name,
            emp.position,
            float(emp.salary),
            emp.employment_status,
            str(emp.hire_date),
            emp.gender or "N/A"
        ])

    summary = {
        "total_employees": len(employees),
        "total_salary_expense": float(total_salary),
        "average_salary": round(float(total_salary / len(employees)), 2) if employees else 0.0
    }
    return headers, rows, summary

# 2. Department Report
def generate_department_report(db: Session) -> Tuple[List[str], List[List[Any]], Dict[str, Any]]:
    headers = ["Department ID", "Department Name", "Description", "Headcount", "Total Monthly Payroll"]
    departments = db.query(Department).order_by(Department.name.asc()).all()

    rows = []
    total_headcount = 0
    total_payroll = Decimal("0.00")

    for dept in departments:
        emps = db.query(Employee).filter(
            Employee.department_id == dept.id,
            Employee.employment_status == "ACTIVE"
        ).all()
        headcount = len(emps)
        payroll = sum((e.salary for e in emps), Decimal("0.00"))

        total_headcount += headcount
        total_payroll += payroll

        rows.append([
            dept.id,
            dept.name,
            dept.description or "N/A",
            headcount,
            float(payroll)
        ])

    summary = {
        "total_departments": len(departments),
        "total_headcount": total_headcount,
        "total_payroll": float(total_payroll)
    }
    return headers, rows, summary

# 3. Attendance Report
def generate_attendance_report(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    department_id: Optional[int] = None,
    employee_id: Optional[int] = None
) -> Tuple[List[str], List[List[Any]], Dict[str, Any]]:
    headers = ["Date", "Employee Code", "Employee Name", "Department", "Check In", "Check Out", "Work Hours", "Status", "Late?"]
    query = db.query(Attendance).options(
        joinedload(Attendance.employee).joinedload(Employee.department)
    )

    if start_date:
        query = query.filter(Attendance.date >= start_date)
    if end_date:
        query = query.filter(Attendance.date <= end_date)
    if employee_id:
        query = query.filter(Attendance.employee_id == employee_id)
    if department_id:
        query = query.join(Employee, Employee.id == Attendance.employee_id).filter(
            Employee.department_id == department_id
        )

    records = query.order_by(Attendance.date.desc(), Attendance.id.desc()).all()

    rows = []
    total_hours = Decimal("0.00")
    present_count = 0
    late_count = 0

    for rec in records:
        emp_name = rec.employee.full_name if rec.employee else "N/A"
        emp_code = rec.employee.employee_code if rec.employee else "N/A"
        dept_name = rec.employee.department.name if rec.employee and rec.employee.department else "N/A"
        total_hours += rec.work_hours
        if rec.status in {"PRESENT", "LATE"}:
            present_count += 1
        if rec.is_late:
            late_count += 1

        rows.append([
            str(rec.date),
            emp_code,
            emp_name,
            dept_name,
            str(rec.check_in) if rec.check_in else "N/A",
            str(rec.check_out) if rec.check_out else "N/A",
            float(rec.work_hours),
            rec.status,
            "Yes" if rec.is_late else "No"
        ])

    summary = {
        "total_records": len(records),
        "present_count": present_count,
        "late_count": late_count,
        "total_hours_logged": float(total_hours)
    }
    return headers, rows, summary

# 4. Leave Report
def generate_leave_report(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status_filter: Optional[str] = None,
    employee_id: Optional[int] = None
) -> Tuple[List[str], List[List[Any]], Dict[str, Any]]:
    headers = ["ID", "Employee Code", "Employee Name", "Leave Type", "Start Date", "End Date", "Days", "Status", "Reason", "Rejection Remarks"]
    query = db.query(Leave).options(joinedload(Leave.employee))

    if start_date:
        query = query.filter(Leave.start_date >= start_date)
    if end_date:
        query = query.filter(Leave.end_date <= end_date)
    if status_filter:
        query = query.filter(Leave.status == status_filter.upper())
    if employee_id:
        query = query.filter(Leave.employee_id == employee_id)

    leaves = query.order_by(Leave.id.desc()).all()

    rows = []
    approved_days = 0
    for lv in leaves:
        emp_name = lv.employee.full_name if lv.employee else "N/A"
        emp_code = lv.employee.employee_code if lv.employee else "N/A"
        if lv.status == "APPROVED":
            approved_days += lv.days_count

        rows.append([
            lv.id,
            emp_code,
            emp_name,
            lv.leave_type,
            str(lv.start_date),
            str(lv.end_date),
            lv.days_count,
            lv.status,
            lv.reason or "N/A",
            lv.rejection_reason or "N/A"
        ])

    summary = {
        "total_applications": len(leaves),
        "approved_days": approved_days,
        "approved_count": sum(1 for l in leaves if l.status == "APPROVED"),
        "pending_count": sum(1 for l in leaves if l.status == "PENDING"),
        "rejected_count": sum(1 for l in leaves if l.status == "REJECTED")
    }
    return headers, rows, summary

# 5. Salary Report
def generate_salary_report(
    db: Session,
    year: Optional[int] = None,
    month: Optional[int] = None,
    department_id: Optional[int] = None
) -> Tuple[List[str], List[List[Any]], Dict[str, Any]]:
    headers = ["Payment Date", "Employee Code", "Employee Name", "Department", "Basic Salary", "Allowances", "Deductions", "Net Salary", "Method", "Status"]
    query = db.query(Salary).options(
        joinedload(Salary.employee).joinedload(Employee.department)
    )

    if year:
        query = query.filter(func.extract("year", Salary.payment_date) == year)
    if month:
        query = query.filter(func.extract("month", Salary.payment_date) == month)
    if department_id:
        query = query.join(Employee, Employee.id == Salary.employee_id).filter(
            Employee.department_id == department_id
        )

    salaries = query.order_by(Salary.payment_date.desc()).all()

    rows = []
    total_net = Decimal("0.00")
    total_paid = Decimal("0.00")

    for sal in salaries:
        emp_name = sal.employee.full_name if sal.employee else "N/A"
        emp_code = sal.employee.employee_code if sal.employee else "N/A"
        dept_name = sal.employee.department.name if sal.employee and sal.employee.department else "N/A"

        total_net += sal.net_salary
        if sal.status == "PAID":
            total_paid += sal.net_salary

        rows.append([
            str(sal.payment_date),
            emp_code,
            emp_name,
            dept_name,
            float(sal.basic_salary),
            float(sal.allowances),
            float(sal.deductions),
            float(sal.net_salary),
            sal.payment_method,
            sal.status
        ])

    summary = {
        "total_records": len(salaries),
        "total_payout": float(total_net),
        "total_paid": float(total_paid)
    }
    return headers, rows, summary

# Exporters
def export_to_csv(headers: List[str], rows: List[List[Any]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue()

def export_to_excel(headers: List[str], rows: List[List[Any]], sheet_name: str = "Report") -> io.BytesIO:
    return create_xlsx(headers, rows, sheet_name=sheet_name)
