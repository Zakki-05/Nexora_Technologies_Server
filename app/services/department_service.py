from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status
from app.models.department import Department
from app.models.employee import Employee
from app.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentResponse
from app.schemas.employee import EmployeeResponse
from app.schemas.common import PaginatedResponse
from app.utils.pagination import paginate

def get_department_employee_count(department_id: int, db: Session) -> int:
    return db.query(Employee).filter(Employee.department_id == department_id).count()

def get_all_departments(
    db: Session,
    page: int = 1,
    size: int = 50,
    search: Optional[str] = None
) -> PaginatedResponse[DepartmentResponse]:
    query = db.query(
        Department,
        func.count(Employee.id).label("emp_count")
    ).outerjoin(
        Employee, Employee.department_id == Department.id
    ).group_by(Department.id)

    if search:
        query = query.filter(Department.name.ilike(f"%{search}%"))

    query = query.order_by(Department.name.asc())
    total = query.count()

    offset = (page - 1) * size
    results = query.offset(offset).limit(size).all()

    items = []
    for dept, count in results:
        resp = DepartmentResponse.model_validate(dept)
        resp.employee_count = count
        items.append(resp)

    import math
    pages = math.ceil(total / size) if total > 0 else 1

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages
    )

def get_all_departments_list(db: Session) -> List[DepartmentResponse]:
    # Single optimized query with outerjoin and group_by to eliminate N+1 queries
    query_results = (
        db.query(Department, func.count(Employee.id).label("emp_count"))
        .outerjoin(Employee, Employee.department_id == Department.id)
        .group_by(Department.id)
        .order_by(Department.name.asc())
        .all()
    )
    results = []
    for dept, count in query_results:
        resp = DepartmentResponse.model_validate(dept)
        resp.employee_count = count
        results.append(resp)
    return results

def get_department_by_id(department_id: int, db: Session) -> DepartmentResponse:
    department = db.query(Department).filter(Department.id == department_id).first()
    if not department:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found"
        )
    count = db.query(Employee).filter(Employee.department_id == department_id).count()
    resp = DepartmentResponse.model_validate(department)
    resp.employee_count = count
    return resp

def create_department(data: DepartmentCreate, db: Session) -> DepartmentResponse:
    existing = db.query(Department).filter(
        Department.name.ilike(data.name.strip())
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Department with name '{data.name}' already exists"
        )

    try:
        department = Department(
            name=data.name.strip(),
            description=data.description
        )
        db.add(department)
        db.commit()
        db.refresh(department)

        resp = DepartmentResponse.model_validate(department)
        resp.employee_count = 0
        return resp
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create department: {str(exc)}"
        )

def update_department(department_id: int, data: DepartmentUpdate, db: Session) -> DepartmentResponse:
    department = db.query(Department).filter(Department.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")

    existing = db.query(Department).filter(
        Department.name.ilike(data.name.strip()),
        Department.id != department_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Another department named '{data.name}' already exists"
        )

    try:
        department.name = data.name.strip()
        department.description = data.description
        db.commit()
        db.refresh(department)

        return get_department_by_id(department_id, db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update department: {str(exc)}"
        )

def get_department_employees(
    department_id: int,
    db: Session,
    page: int = 1,
    size: int = 20
) -> PaginatedResponse[EmployeeResponse]:
    # Ensure department exists
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    query = db.query(Employee).filter(
        Employee.department_id == department_id
    ).order_by(Employee.id.desc())

    return paginate(query, page, size)

def reassign_employees(source_dept_id: int, target_dept_id: int, db: Session) -> dict:
    if source_dept_id == target_dept_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and target departments cannot be the same"
        )

    source = db.query(Department).filter(Department.id == source_dept_id).first()
    target = db.query(Department).filter(Department.id == target_dept_id).first()

    if not source:
        raise HTTPException(status_code=404, detail="Source department not found")
    if not target:
        raise HTTPException(status_code=404, detail="Target department not found")

    try:
        count = db.query(Employee).filter(Employee.department_id == source_dept_id).update(
            {"department_id": target_dept_id}
        )
        db.commit()
        return {
            "message": f"Successfully reassigned {count} employees to {target.name}",
            "reassigned_count": count,
            "success": True
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reassign employees: {str(exc)}"
        )

def delete_department(
    department_id: int,
    db: Session,
    reassign_to: Optional[int] = None
) -> dict:
    department = db.query(Department).filter(Department.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")

    emp_count = db.query(Employee).filter(Employee.department_id == department_id).count()

    if emp_count > 0:
        if not reassign_to:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete department containing {emp_count} employees. Reassign employees first or specify target department."
            )
        reassign_employees(department_id, reassign_to, db)

    try:
        db.delete(department)
        db.commit()
        return {
            "message": f"Department '{department.name}' deleted successfully",
            "success": True
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete department: {str(exc)}"
        )
