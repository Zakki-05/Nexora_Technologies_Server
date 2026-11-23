from datetime import date
from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.attendance import (
    AttendanceManualCreate,
    AttendanceUpdate,
    AttendanceResponse,
    AttendanceLiveStatusResponse,
    DailyAttendanceTimelineResponse,
    WeeklyAttendanceSummaryResponse,
    MonthlyAttendanceDetailedResponse,
    AttendanceSummary,
    DailyAttendanceReport,
    AttendanceCorrectionCreate,
    AttendanceCorrectionReview,
    AttendanceCorrectionResponse
)
from app.schemas.common import PaginatedResponse
from app.services import attendance_service
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import get_current_admin

router = APIRouter()

def get_employee_id(current_user: User, db: Session) -> int:
    from app.services.employee_service import ensure_employee_profile
    emp = ensure_employee_profile(current_user, db)
    return emp.id

@router.post("/check-in", response_model=AttendanceResponse)
def check_in(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    employee_id = get_employee_id(current_user, db)
    return attendance_service.check_in(employee_id, db)

@router.post("/check-out", response_model=AttendanceResponse)
def check_out(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    employee_id = get_employee_id(current_user, db)
    return attendance_service.check_out(employee_id, db)

@router.get("/live-status", response_model=AttendanceLiveStatusResponse)
def get_live_status(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    employee_id = get_employee_id(current_user, db)
    return attendance_service.get_live_status(employee_id, db)

@router.get("/timeline", response_model=DailyAttendanceTimelineResponse)
@router.get("/timeline/{target_date}", response_model=DailyAttendanceTimelineResponse)
def get_daily_timeline(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    target_date: Optional[date] = None
):
    employee_id = get_employee_id(current_user, db)
    resolved_date = target_date or date.today()
    return attendance_service.get_daily_timeline(employee_id, resolved_date, db)

@router.get("/weekly", response_model=WeeklyAttendanceSummaryResponse)
@router.get("/weekly-hours", response_model=WeeklyAttendanceSummaryResponse)
def get_weekly_summary(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    start_date: Optional[date] = None
):
    employee_id = get_employee_id(current_user, db)
    return attendance_service.get_weekly_summary(employee_id, start_date, db)

@router.get("/monthly-details", response_model=MonthlyAttendanceDetailedResponse)
def get_monthly_details(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    year: int = Query(default=date.today().year),
    month: int = Query(default=date.today().month, ge=1, le=12)
):
    employee_id = get_employee_id(current_user, db)
    return attendance_service.get_monthly_detailed_summary(employee_id, year, month, db)

@router.get("/today", response_model=Optional[AttendanceResponse])
def get_today_attendance(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    employee_id = get_employee_id(current_user, db)
    return attendance_service.get_today_attendance(employee_id, db)

@router.get("/my-attendance", response_model=PaginatedResponse[AttendanceResponse])
def get_my_attendance(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    employee_id = get_employee_id(current_user, db)
    return attendance_service.get_employee_attendance(
        employee_id=employee_id,
        db=db,
        page=page,
        size=size,
        start_date=start_date,
        end_date=end_date
    )

@router.get("/my-summary", response_model=AttendanceSummary)
def get_my_monthly_summary(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    year: int = Query(default=date.today().year),
    month: int = Query(default=date.today().month, ge=1, le=12)
):
    employee_id = get_employee_id(current_user, db)
    return attendance_service.get_employee_monthly_summary(
        employee_id=employee_id,
        year=year,
        month=month,
        db=db
    )

# Regularization / Correction endpoints
@router.post("/corrections", response_model=AttendanceCorrectionResponse, status_code=status.HTTP_201_CREATED)
@router.post("/regularize", response_model=AttendanceCorrectionResponse, status_code=status.HTTP_201_CREATED)
def request_correction(
    data: AttendanceCorrectionCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    employee_id = get_employee_id(current_user, db)
    return attendance_service.create_correction_request(employee_id, data, db)

@router.get("/corrections/my", response_model=List[AttendanceCorrectionResponse])
def get_my_corrections(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    employee_id = get_employee_id(current_user, db)
    return attendance_service.get_employee_corrections(employee_id, db)

@router.get("/corrections/pending", response_model=List[AttendanceCorrectionResponse])
def get_pending_corrections(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return attendance_service.get_pending_corrections(db)

@router.patch("/corrections/{correction_id}/review", response_model=AttendanceCorrectionResponse)
def review_correction(
    correction_id: int,
    data: AttendanceCorrectionReview,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return attendance_service.review_correction_request(correction_id, admin.id, data, db)

# Administrative endpoints
@router.get("/", response_model=PaginatedResponse[AttendanceResponse])
def get_all_attendance(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    date_filter: Optional[date] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    department_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    employee_id: Optional[int] = None
):
    return attendance_service.get_all_attendance(
        db=db,
        page=page,
        size=size,
        date_filter=date_filter,
        start_date=start_date,
        end_date=end_date,
        department_id=department_id,
        status_filter=status_filter,
        employee_id=employee_id
    )

@router.get("/employee/{employee_id}", response_model=PaginatedResponse[AttendanceResponse])
def get_employee_attendance_records(
    employee_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    return attendance_service.get_employee_attendance(
        employee_id=employee_id,
        db=db,
        page=page,
        size=size,
        start_date=start_date,
        end_date=end_date
    )

@router.get("/reports/daily", response_model=DailyAttendanceReport)
def get_daily_attendance_report(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    report_date: date = Query(default=date.today())
):
    return attendance_service.get_daily_report(report_date, db)

@router.post("/manual", response_model=AttendanceResponse)
def manual_record_attendance(
    data: AttendanceManualCreate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return attendance_service.manual_record_attendance(data, db)

@router.put("/{attendance_id}", response_model=AttendanceResponse)
def correct_attendance(
    attendance_id: int,
    data: AttendanceUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return attendance_service.correct_attendance(attendance_id, data, db)
