from typing import Annotated, List, Optional
from datetime import date
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.break_session import (
    BreakStartRequest,
    BreakSessionResponse,
    BreakStatusResponse
)
from app.services import break_service
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import get_current_admin

router = APIRouter()

def get_employee_id(current_user: User, db: Session) -> int:
    from app.services.employee_service import ensure_employee_profile
    emp = ensure_employee_profile(current_user, db)
    return emp.id

@router.post("/start", response_model=BreakSessionResponse, status_code=status.HTTP_201_CREATED)
def start_break(
    data: BreakStartRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    employee_id = get_employee_id(current_user, db)
    return break_service.start_break(
        employee_id=employee_id,
        break_type=data.break_type,
        remarks=data.remarks,
        db=db
    )

@router.post("/end", response_model=BreakSessionResponse)
def end_break(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    employee_id = get_employee_id(current_user, db)
    return break_service.end_break(employee_id, db)

@router.get("/status", response_model=BreakStatusResponse)
def get_break_status(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    employee_id = get_employee_id(current_user, db)
    return break_service.get_break_status(employee_id, db)

@router.get("/today", response_model=List[BreakSessionResponse])
def get_today_breaks(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    employee_id = get_employee_id(current_user, db)
    return break_service.get_employee_breaks_for_date(employee_id, date.today(), db)

@router.get("/employee/{employee_id}", response_model=List[BreakSessionResponse])
def get_employee_breaks_by_admin(
    employee_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    target_date: Optional[date] = None
):
    d = target_date or date.today()
    return break_service.get_employee_breaks_for_date(employee_id, d, db)
