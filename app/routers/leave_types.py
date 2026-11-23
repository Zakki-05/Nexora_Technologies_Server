from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.leave import (
    LeaveTypeCreate,
    LeaveTypeUpdate,
    LeaveTypeResponse
)
from app.schemas.common import MessageResponse
from app.services import leave_service
from app.dependencies.permissions import get_current_admin
from app.dependencies.auth import get_current_user

router = APIRouter()

@router.get("/", response_model=List[LeaveTypeResponse])
def get_leave_types(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    active_only: bool = Query(True)
):
    """
    List all corporate leave types.
    Employees see active leave types; Admins can see all by active_only=False.
    """
    if current_user.role not in ["ADMIN", "SUPER_ADMIN"]:
        active_only = True
    return leave_service.get_all_leave_types(db=db, active_only=active_only)

@router.post("/", response_model=LeaveTypeResponse, status_code=status.HTTP_201_CREATED)
def create_leave_type(
    data: LeaveTypeCreate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    """
    Create a new corporate leave type (Admin/SuperAdmin only).
    """
    return leave_service.create_leave_type(data, db)

@router.get("/{leave_type_id}", response_model=LeaveTypeResponse)
def get_leave_type_detail(
    leave_type_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Retrieve details of a single leave type.
    """
    return leave_service.get_leave_type_by_id(leave_type_id, db)

@router.patch("/{leave_type_id}", response_model=LeaveTypeResponse)
def update_leave_type(
    leave_type_id: int,
    data: LeaveTypeUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    """
    Update configuration/rules of a corporate leave type (Admin/SuperAdmin only).
    """
    return leave_service.update_leave_type(leave_type_id, data, db)

@router.delete("/{leave_type_id}", response_model=MessageResponse)
def delete_or_deactivate_leave_type(
    leave_type_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    """
    Delete or deactivate a corporate leave type (Admin/SuperAdmin only).
    """
    return leave_service.delete_leave_type(leave_type_id, db)
