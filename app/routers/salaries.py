from typing import Annotated, Optional
from fastapi import APIRouter, Depends, status, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.salary import Salary
from app.schemas.salary import (
    SalaryCreate,
    SalaryUpdate,
    SalaryResponse,
    SalarySummary,
    SalaryStructureResponse,
    SalaryStructureUpdate,
    SalaryStructurePreviewRequest,
    SalaryStructurePreviewResponse,
    PayrollRunRequest,
    PayrollRunResponse
)
from app.schemas.common import PaginatedResponse, MessageResponse
from app.services import salary_service
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import get_current_admin

router = APIRouter()

def get_employee_id(current_user: User, db: Session) -> int:
    from app.services.employee_service import ensure_employee_profile
    emp = ensure_employee_profile(current_user, db)
    return emp.id

# ==================== SALARY STRUCTURE ENDPOINTS ====================

@router.get("/structures", response_model=PaginatedResponse[SalaryStructureResponse])
def get_all_salary_structures(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100)
):
    """List all corporate salary structures (Admin/SuperAdmin only)."""
    return salary_service.get_all_salary_structures(db=db, page=page, size=size)

@router.get("/structures/{employee_id}", response_model=SalaryStructureResponse)
def get_employee_salary_structure(
    employee_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Retrieve salary structure for an employee."""
    user_role = current_user.role.strip().upper()
    if user_role not in ["ADMIN", "SUPER_ADMIN"]:
        emp_id = get_employee_id(current_user, db)
        if emp_id != employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only access your own salary structure"
            )
    return salary_service.get_salary_structure(employee_id, db)

@router.patch("/structures/{employee_id}", response_model=SalaryStructureResponse)
@router.put("/structures/{employee_id}", response_model=SalaryStructureResponse)
def update_employee_salary_structure(
    employee_id: int,
    data: SalaryStructureUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    """Update statutory salary components and deduction rates for an employee."""
    return salary_service.update_salary_structure(employee_id, data, db)

@router.post("/structures/preview", response_model=SalaryStructurePreviewResponse)
def preview_salary_structure(
    data: SalaryStructurePreviewRequest,
    admin: Annotated[User, Depends(get_current_admin)]
):
    """Simulate and preview monthly/annual salary components and take-home pay."""
    return salary_service.preview_salary_structure(data)

# ==================== MONTHLY PAYROLL RUN ENGINE ====================

@router.post("/run", response_model=PayrollRunResponse)
def run_payroll(
    data: PayrollRunRequest,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    """
    Execute organization-wide monthly payroll calculation:
    - PREVIEW: Simulate payroll numbers without committing.
    - PROCESS: Compute, deduct statutory PF/PT/ESI/TDS/LOP, and save salary records.
    - LOCK: Lock payroll period to prevent alterations.
    """
    return salary_service.run_monthly_payroll(data, db)

# ==================== PDF PAYSLIP DOWNLOADS ====================

@router.get("/{salary_id}/payslip")
def download_payslip_pdf(
    salary_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Download a printable, high-resolution PDF payslip."""
    salary = salary_service.get_salary_by_id(salary_id, db)
    user_role = current_user.role.strip().upper()
    if user_role not in ["ADMIN", "SUPER_ADMIN"]:
        emp_id = get_employee_id(current_user, db)
        if salary.employee_id != emp_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only download your own payslips"
            )

    pdf_bytes, filename = salary_service.get_payslip_pdf(salary_id, db)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"'
        }
    )

@router.get("/my-salary/{salary_id}/payslip")
def download_my_payslip_pdf(
    salary_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Self-service endpoint for employees to download their own payslip."""
    return download_payslip_pdf(salary_id, db, current_user)

# ==================== CORE SALARY RECORD APIS ====================

@router.get("/", response_model=PaginatedResponse[SalaryResponse])
def get_salaries(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    employee_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    year: Optional[int] = None,
    month: Annotated[Optional[int], Query(ge=1, le=12)] = None
):
    return salary_service.get_all_salaries(
        db=db,
        page=page,
        size=size,
        employee_id=employee_id,
        status_filter=status_filter,
        year=year,
        month=month
    )

@router.get("/my-salary", response_model=PaginatedResponse[SalaryResponse])
def get_my_salary_history(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100)
):
    employee_id = get_employee_id(current_user, db)
    return salary_service.get_employee_salaries(
        employee_id=employee_id,
        db=db,
        page=page,
        size=size
    )

@router.get("/summary", response_model=SalarySummary)
def get_salary_summary(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    year: Optional[int] = None,
    month: Annotated[Optional[int], Query(ge=1, le=12)] = None
):
    return salary_service.get_salary_summary(db=db, year=year, month=month)

@router.get("/{salary_id}", response_model=SalaryResponse)
def get_salary_record(
    salary_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    salary = salary_service.get_salary_by_id(salary_id, db)
    user_role = current_user.role.strip().upper()

    if user_role not in ["ADMIN", "SUPER_ADMIN"]:
        emp_id = get_employee_id(current_user, db)
        if salary.employee_id != emp_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only access your own salary details"
            )
    return salary_service.format_salary_response(salary)

@router.post("/", response_model=SalaryResponse, status_code=status.HTTP_201_CREATED)
def create_salary(
    data: SalaryCreate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    salary = salary_service.create_salary_record(data, db)
    return salary_service.format_salary_response(salary)

@router.put("/{salary_id}", response_model=SalaryResponse)
def update_salary(
    salary_id: int,
    data: SalaryUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    salary = salary_service.update_salary(salary_id, data, db)
    return salary_service.format_salary_response(salary)

@router.delete("/{salary_id}", response_model=MessageResponse)
def delete_salary(
    salary_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return salary_service.delete_salary(salary_id, db)
