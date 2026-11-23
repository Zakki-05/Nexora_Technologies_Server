from datetime import date
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status
from app.models.holiday import Holiday
from app.schemas.holiday import HolidayCreate, HolidayUpdate, HolidayResponse

def get_all_holidays(db: Session, year: Optional[int] = None) -> List[Holiday]:
    query = db.query(Holiday)
    if year:
        query = query.filter(func.extract("year", Holiday.date) == year)
    return query.order_by(Holiday.date.asc()).all()

def get_upcoming_holidays(db: Session, limit: int = 5) -> List[Holiday]:
    today = date.today()
    return db.query(Holiday).filter(
        Holiday.date >= today
    ).order_by(Holiday.date.asc()).limit(limit).all()

def get_holiday_by_id(holiday_id: int, db: Session) -> Holiday:
    holiday = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if not holiday:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Holiday not found"
        )
    return holiday

def create_holiday(data: HolidayCreate, db: Session) -> Holiday:
    existing = db.query(Holiday).filter(Holiday.date == data.date).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A holiday '{existing.name}' is already registered on {data.date}"
        )

    try:
        holiday = Holiday(
            name=data.name.strip(),
            date=data.date,
            description=data.description,
            is_optional=data.is_optional
        )
        db.add(holiday)
        db.commit()
        db.refresh(holiday)
        return holiday
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create holiday: {str(exc)}"
        )

def update_holiday(holiday_id: int, data: HolidayUpdate, db: Session) -> Holiday:
    holiday = get_holiday_by_id(holiday_id, db)
    update_data = data.model_dump(exclude_unset=True)

    if "date" in update_data and update_data["date"] is not None:
        existing = db.query(Holiday).filter(
            Holiday.date == update_data["date"],
            Holiday.id != holiday_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A holiday '{existing.name}' is already registered on {update_data['date']}"
            )

    try:
        for key, value in update_data.items():
            setattr(holiday, key, value)
        db.commit()
        db.refresh(holiday)
        return holiday
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update holiday: {str(exc)}"
        )

def delete_holiday(holiday_id: int, db: Session) -> dict:
    holiday = get_holiday_by_id(holiday_id, db)
    try:
        db.delete(holiday)
        db.commit()
        return {"message": f"Holiday '{holiday.name}' deleted successfully", "success": True}
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete holiday: {str(exc)}"
        )
