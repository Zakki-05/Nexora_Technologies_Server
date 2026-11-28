from typing import Any
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.employee import Employee
from app.models.user import User


def list_departments_summary(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    """Return organization departments and active headcounts."""
    rows = (
        db.query(Department.id, Department.name, func.count(Employee.id))
        .outerjoin(
            Employee,
            (Employee.department_id == Department.id)
            & (Employee.organization_id == user.organization_id),
        )
        .filter(Department.organization_id == user.organization_id)
        .group_by(Department.id, Department.name)
        .order_by(Department.name.asc())
        .all()
    )
    return {
        "organization_id": user.organization_id,
        "department_count": len(rows),
        "departments": [
            {"id": dept_id, "name": name, "employee_count": int(cnt)}
            for dept_id, name, cnt in rows
        ],
    }
