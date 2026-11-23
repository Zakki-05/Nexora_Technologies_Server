from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.leave import Leave
from app.schemas.leave import (
    LeaveCreate,
    LeaveDecision,
    LeaveResponse,
    LeaveBalanceResponse,
    LeaveBalanceUpdate,
    LeaveTransactionResponse,
    LeaveAdjustmentRequest
)
from app.schemas.common import PaginatedResponse, MessageResponse
from app.services import leave_service
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import get_current_admin

router = APIRouter()

def get_employee_id(current_user: User, db: Session) -> int:
    from app.services.employee_service import ensure_employee_profile
    emp = ensure_employee_profile(current_user, db)
    return emp.id

@router.post("/", response_model=LeaveResponse, status_code=status.HTTP_201_CREATED)
def apply_for_leave(
    data: LeaveCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    employee_id = get_employee_id(current_user, db)
    return leave_service.apply_leave(employee_id, data, db)

@router.get("/my-leaves", response_model=PaginatedResponse[LeaveResponse])
def get_my_leaves(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = None
):
    employee_id = get_employee_id(current_user, db)
    return leave_service.get_employee_leaves(
        employee_id=employee_id,
        db=db,
        page=page,
        size=size,
        status_filter=status_filter
    )

@router.get("/my-balances", response_model=LeaveBalanceResponse)
def get_my_leave_balances(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    employee_id = get_employee_id(current_user, db)
    return leave_service.get_employee_balance(employee_id, db)

@router.get("/ledger", response_model=PaginatedResponse[LeaveTransactionResponse])
def get_my_leave_ledger(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    leave_type_id: Optional[int] = None
):
    employee_id = get_employee_id(current_user, db)
    return leave_service.get_leave_ledger(
        employee_id=employee_id,
        db=db,
        page=page,
        size=size,
        leave_type_id=leave_type_id
    )

@router.patch("/{leave_id}/cancel", response_model=LeaveResponse)
def cancel_leave(
    leave_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    if current_user.role not in ["ADMIN", "SUPER_ADMIN"]:
        employee_id = get_employee_id(current_user, db)
        leave = db.query(Leave).filter(Leave.id == leave_id).first()
        if not leave or leave.employee_id != employee_id:
            raise HTTPException(status_code=403, detail="Not authorized to cancel this leave request")
    return leave_service.cancel_leave(leave_id, current_user.id, db)

@router.get("/", response_model=PaginatedResponse[LeaveResponse])
def get_all_leaves(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = None,
    department_id: Optional[int] = None,
    employee_id: Optional[int] = None
):
    return leave_service.get_all_leaves(
        db=db,
        page=page,
        size=size,
        status_filter=status_filter,
        department_id=department_id,
        employee_id=employee_id
    )

@router.get("/employee/{employee_id}", response_model=PaginatedResponse[LeaveResponse])
def get_employee_leave_history(
    employee_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = None
):
    return leave_service.get_employee_leaves(
        employee_id=employee_id,
        db=db,
        page=page,
        size=size,
        status_filter=status_filter
    )

@router.patch("/{leave_id}/review", response_model=LeaveResponse)
def review_leave(
    leave_id: int,
    data: LeaveDecision,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return leave_service.review_leave(leave_id, data, admin.id, db)

@router.get("/balances/{employee_id}", response_model=LeaveBalanceResponse)
def get_employee_balances(
    employee_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return leave_service.get_employee_balance(employee_id, db)

@router.patch("/balances/{employee_id}", response_model=LeaveBalanceResponse)
def update_employee_balances(
    employee_id: int,
    data: LeaveBalanceUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return leave_service.update_employee_balance(employee_id, data, db)

@router.post("/adjust-balance", response_model=LeaveTransactionResponse)
def adjust_leave_balance(
    data: LeaveAdjustmentRequest,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return leave_service.adjust_leave_balance(data, admin.id, db)

@router.get("/ledger/{employee_id}", response_model=PaginatedResponse[LeaveTransactionResponse])
def get_employee_ledger(
    employee_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    leave_type_id: Optional[int] = None
):
    return leave_service.get_leave_ledger(
        employee_id=employee_id,
        db=db,
        page=page,
        size=size,
        leave_type_id=leave_type_id
    )

@router.delete("/{leave_id}", response_model=MessageResponse)
def delete_leave(
    leave_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    return leave_service.delete_leave(leave_id, db)
