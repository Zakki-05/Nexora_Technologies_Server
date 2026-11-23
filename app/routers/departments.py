from typing import Annotated, Optional, List, Union
from fastapi import APIRouter, Depends, status, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.department import (
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentResponse,
    DepartmentReassign
)
from app.schemas.employee import EmployeeResponse
from app.schemas.common import PaginatedResponse, MessageResponse
from app.services import department_service
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import get_current_admin

router = APIRouter()

@router.get("/", response_model=Union[PaginatedResponse[DepartmentResponse], List[DepartmentResponse]])
def get_departments(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    all: bool = Query(False, description="Return full list for select dropdowns")
):
    if all:
        return department_service.get_all_departments_list(db)
    return department_service.get_all_departments(db, page=page, size=size, search=search)

@router.get("/{department_id}", response_model=DepartmentResponse)
def get_department(
    department_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    return department_service.get_department_by_id(department_id, db)

@router.get("/{department_id}/employees", response_model=PaginatedResponse[EmployeeResponse])
def get_department_employees(
    department_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100)
):
    return department_service.get_department_employees(department_id, db, page=page, size=size)

@router.post("/", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department(
    data: DepartmentCreate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return department_service.create_department(data, db)

@router.put("/{department_id}", response_model=DepartmentResponse)
def update_department(
    department_id: int,
    data: DepartmentUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return department_service.update_department(department_id, data, db)

@router.post("/{department_id}/reassign", response_model=MessageResponse)
def reassign_department_employees(
    department_id: int,
    data: DepartmentReassign,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    res = department_service.reassign_employees(department_id, data.target_department_id, db)
    return {"message": res["message"], "success": True}

@router.delete("/{department_id}", response_model=MessageResponse)
def delete_department(
    department_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    reassign_to: Optional[int] = Query(None, description="Department ID to reassign employees to before deletion")
):
    res = department_service.delete_department(department_id, db, reassign_to=reassign_to)
    return {"message": res["message"], "success": True}
