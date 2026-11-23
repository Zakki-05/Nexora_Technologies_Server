from datetime import date, time, datetime
from decimal import Decimal
from typing import Literal, Optional, List, Any
from pydantic import BaseModel, ConfigDict, Field, computed_field
from app.schemas.break_session import BreakSessionResponse

class EmployeeShortInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    employee_code: str
    position: str
    department_id: int

class AttendanceSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    attendance_id: int
    employee_id: int
    session_number: int
    punch_in: datetime
    punch_out: Optional[datetime] = None
    duration_minutes: int = 0
    status: str
    created_at: Optional[datetime] = None

class AttendanceManualCreate(BaseModel):
    employee_id: int = Field(gt=0)
    date: date
    check_in: Optional[time] = None
    check_out: Optional[time] = None
    status: Literal["PRESENT", "ABSENT", "HALF_DAY", "LATE"] = "PRESENT"
    remarks: Optional[str] = None

class AttendanceUpdate(BaseModel):
    check_in: Optional[time] = None
    check_out: Optional[time] = None
    status: Optional[Literal["PRESENT", "ABSENT", "HALF_DAY", "LATE", "INCOMPLETE"]] = None
    remarks: Optional[str] = None

class AttendanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    date: date
    check_in: Optional[time] = None
    check_out: Optional[time] = None
    work_hours: Decimal = Decimal("0.00")

    @computed_field
    @property
    def working_hours(self) -> Decimal:
        return self.work_hours

    @computed_field
    @property
    def is_punched_in(self) -> bool:
        if self.sessions:
            return any(s.punch_out is None for s in self.sessions)
        return self.check_in is not None and self.check_out is None

    office_duration_minutes: int = 0
    actual_working_minutes: int = 0
    total_break_minutes: int = 0
    paid_break_minutes: int = 0
    unpaid_break_minutes: int = 0
    overtime_minutes: int = 0
    is_late: bool = False
    is_incomplete: bool = False
    status: str
    remarks: Optional[str] = None
    created_at: Optional[datetime] = None
    employee: Optional[EmployeeShortInfo] = None
    sessions: Optional[List[AttendanceSessionResponse]] = None
    breaks: Optional[List[BreakSessionResponse]] = None

class AttendanceLiveStatusResponse(BaseModel):
    is_punched_in: bool = False
    active_session_number: Optional[int] = None
    session_punch_in: Optional[datetime] = None
    is_on_break: bool = False
    current_break_type: Optional[str] = None
    break_start_time: Optional[datetime] = None
    first_punch_in: Optional[time] = None
    last_punch_out: Optional[time] = None
    today_working_minutes: int = 0
    today_break_minutes: int = 0
    office_duration_minutes: int = 0
    required_working_minutes: int = 480
    remaining_working_minutes: int = 0
    overtime_minutes: int = 0
    status: str = "ABSENT"
    is_late: bool = False
    total_sessions_count: int = 0
    total_breaks_count: int = 0
    sessions: List[AttendanceSessionResponse] = []
    breaks: List[BreakSessionResponse] = []

class TimelineEvent(BaseModel):
    time: str
    event_type: str # PUNCH_IN, PUNCH_OUT, BREAK_START, BREAK_END
    title: str
    details: Optional[str] = None

class DailyAttendanceTimelineResponse(BaseModel):
    date: date
    status: str
    is_late: bool
    office_duration_hhmm: str
    total_break_hhmm: str
    actual_work_hhmm: str
    overtime_hhmm: str
    events: List[TimelineEvent] = []

class WeeklyDayItem(BaseModel):
    date: date
    day_name: str
    working_minutes: int = 0
    working_hours_hhmm: str = "00:00"
    break_minutes: int = 0
    status: str = "ABSENT"
    is_late: bool = False

class WeeklyAttendanceSummaryResponse(BaseModel):
    week_start: date
    week_end: date
    days: List[WeeklyDayItem] = []
    total_weekly_working_minutes: int = 0
    total_weekly_working_hhmm: str = "00:00"
    total_weekly_break_minutes: int = 0
    expected_weekly_minutes: int = 2400
    weekly_overtime_minutes: int = 0

class MonthlyAttendanceDetailedResponse(BaseModel):
    year: int
    month: int
    total_calendar_days: int
    total_working_days: int
    present_days: int
    half_days: int
    absent_days: int
    approved_leave_days: int
    holiday_days: int
    weekly_off_days: int
    total_actual_working_minutes: int
    total_actual_working_hhmm: str
    expected_working_minutes: int
    expected_working_hhmm: str
    remaining_monthly_minutes: int
    total_break_minutes: int
    total_break_hhmm: str
    total_overtime_minutes: int
    total_overtime_hhmm: str
    attendance_percentage: float
    daily_records: List[AttendanceResponse] = []

class AttendanceSummary(BaseModel):
    total_records: int = 0
    present_days: int = 0
    absent_days: int = 0
    late_days: int = 0
    half_days: int = 0
    total_work_hours: Decimal = Decimal("0.00")
    attendance_rate: float = 0.0

class DailyAttendanceReport(BaseModel):
    date: date
    total_employees: int
    present: int
    absent: int
    late: int
    half_day: int
    attendance_rate: float

class AttendanceCorrectionCreate(BaseModel):
    attendance_id: int
    requested_check_in: Optional[time] = None
    requested_check_out: Optional[time] = None
    reason: str = Field(min_length=5, max_length=500)

class AttendanceCorrectionReview(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    review_remarks: str = Field(min_length=3, max_length=500)

class AttendanceCorrectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    attendance_id: int
    employee_id: int
    requested_check_in: Optional[time] = None
    requested_check_out: Optional[time] = None
    reason: str
    status: str
    reviewed_by: Optional[int] = None
    review_remarks: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
