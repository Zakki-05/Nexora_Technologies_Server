from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.holiday import HolidayCreate, HolidayUpdate, HolidayResponse
from app.schemas.common import MessageResponse
from app.services import holiday_service
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import get_current_admin

router = APIRouter()

@router.get("/", response_model=List[HolidayResponse])
def get_holidays(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    year: Optional[int] = Query(None)
):
    return holiday_service.get_all_holidays(db, year=year)

@router.get("/upcoming", response_model=List[HolidayResponse])
def get_upcoming_holidays(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(5, ge=1, le=20)
):
    return holiday_service.get_upcoming_holidays(db, limit=limit)

@router.get("/{holiday_id}", response_model=HolidayResponse)
def get_holiday(
    holiday_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    return holiday_service.get_holiday_by_id(holiday_id, db)

@router.post("/", response_model=HolidayResponse, status_code=status.HTTP_201_CREATED)
def create_holiday(
    data: HolidayCreate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return holiday_service.create_holiday(data, db)

@router.put("/{holiday_id}", response_model=HolidayResponse)
def update_holiday(
    holiday_id: int,
    data: HolidayUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return holiday_service.update_holiday(holiday_id, data, db)

@router.delete("/{holiday_id}", response_model=MessageResponse)
def delete_holiday(
    holiday_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return holiday_service.delete_holiday(holiday_id, db)
