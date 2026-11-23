from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, status, HTTPException, Query, File, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeePatch,
    EmployeeSelfUpdate,
    EmployeeStatusUpdate,
    EmployeeResponse,
    AvatarReviewRequest,
    AvatarPendingRequestResponse
)
from app.schemas.common import PaginatedResponse, MessageResponse
from app.services import employee_service
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import get_current_admin

router = APIRouter()

@router.get("/", response_model=PaginatedResponse[EmployeeResponse])
def get_employees(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    department_id: Optional[int] = None,
    employment_status: Optional[str] = None
):
    return employee_service.get_all_employees(
        db=db,
        page=page,
        size=size,
        search=search,
        department_id=department_id,
        employment_status=employment_status
    )

@router.get("/me", response_model=EmployeeResponse)
def get_my_profile(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    return employee_service.get_employee_by_user_id(current_user.id, db)

@router.patch("/me", response_model=EmployeeResponse)
def update_my_profile(
    data: EmployeeSelfUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    return employee_service.update_my_profile(current_user.id, data, db)

@router.post("/me/avatar", response_model=EmployeeResponse)
def upload_my_avatar(
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Employee uploads an avatar image, placing it in PENDING status until HR reviews and accepts."""
    return employee_service.request_avatar_update(current_user.id, file, db)

@router.get("/avatar-requests/pending", response_model=List[AvatarPendingRequestResponse])
def get_pending_avatar_requests(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    """Admin reviews all pending employee profile photo submissions."""
    return employee_service.get_pending_avatar_requests(db)

@router.post("/{employee_id}/avatar-review", response_model=EmployeeResponse)
def review_avatar_request(
    employee_id: int,
    data: AvatarReviewRequest,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    """Admin approves or rejects an employee profile photo request."""
    return employee_service.review_avatar_request(
        employee_id=employee_id,
        status_decision=data.status,
        rejection_reason=data.rejection_reason,
        admin_user_id=admin.id,
        db=db
    )

@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(
    employee_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    user_role = current_user.role.strip().upper()

    # If EMPLOYEE role, can only view self
    if user_role == "EMPLOYEE":
        if not current_user.employee or current_user.employee.id != employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own employee profile"
            )
    elif user_role not in {"ADMIN", "SUPER_ADMIN"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view employee profiles"
        )

    return employee_service.get_employee_by_id(employee_id, db)

@router.post("/", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
def create_employee(
    data: EmployeeCreate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return employee_service.create_employee(data, db)

@router.put("/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: int,
    data: EmployeeUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return employee_service.update_employee(employee_id, data, db)

@router.patch("/{employee_id}", response_model=EmployeeResponse)
def patch_employee(
    employee_id: int,
    data: EmployeePatch,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return employee_service.patch_employee(employee_id, data, db)

@router.patch("/{employee_id}/status", response_model=EmployeeResponse)
def update_employee_status(
    employee_id: int,
    data: EmployeeStatusUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return employee_service.update_employee_status(employee_id, data.employment_status, db)

@router.delete("/{employee_id}", response_model=MessageResponse)
def delete_employee(
    employee_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    hard_delete: bool = Query(False)
):
    return employee_service.delete_employee(employee_id, db, hard_delete=hard_delete)
