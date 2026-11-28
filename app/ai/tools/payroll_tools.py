from typing import Any
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.salary import Salary
from app.models.user import User


def get_my_latest_salary(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    """Return the authenticated employee's latest salary slip summary."""
    emp = db.query(Employee).filter(
        Employee.user_id == user.id,
        Employee.organization_id == user.organization_id,
    ).first()
    if not emp:
        return {"error": "No employee profile linked to this user."}

    sal = (
        db.query(Salary)
        .filter(Salary.employee_id == emp.id)
        .order_by(Salary.payment_date.desc(), Salary.id.desc())
        .first()
    )
    if not sal:
        return {"employee_code": emp.employee_code, "message": "No salary records found."}

    return {
        "employee_code": emp.employee_code,
        "month": sal.month,
        "year": sal.year,
        "basic_salary": float(sal.basic_salary),
        "allowances": float(sal.allowances),
        "deductions": float(sal.deductions),
        "net_salary": float(sal.net_salary),
        "status": sal.status,
        "payment_date": sal.payment_date.isoformat(),
    }


def get_payroll_summary(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    """Return aggregated organization payroll totals (Finance/Admin only, no bank PII)."""
    query = (
        db.query(
            func.count(Salary.id),
            func.coalesce(func.sum(Salary.net_salary), 0),
            func.coalesce(func.sum(Salary.deductions), 0),
        )
        .join(Employee, Employee.id == Salary.employee_id)
        .filter(Employee.organization_id == user.organization_id)
    )
    if args.get("month") is not None:
        query = query.filter(Salary.month == int(args["month"]))
    if args.get("year") is not None:
        query = query.filter(Salary.year == int(args["year"]))

    count_val, net_total, ded_total = query.one()
    return {
        "organization_id": user.organization_id,
        "month": args.get("month"),
        "year": args.get("year"),
        "payslip_count": int(count_val or 0),
        "total_net_salary": round(float(net_total or 0), 2),
        "total_deductions": round(float(ded_total or 0), 2),
    }
