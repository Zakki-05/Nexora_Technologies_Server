from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, ConfigDict, Field

BreakTypeLiteral = Literal[
    "TEA_BREAK",
    "LUNCH_BREAK",
    "PERSONAL_BREAK",
    "SHORT_BREAK",
    "OTHER_BREAK"
]

class BreakStartRequest(BaseModel):
    break_type: BreakTypeLiteral = "TEA_BREAK"
    remarks: Optional[str] = Field(None, max_length=255)

class BreakSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attendance_id: int
    session_id: Optional[int] = None
    employee_id: int
    break_type: str
    break_start: datetime
    break_end: Optional[datetime] = None
    duration_minutes: int = 0
    is_paid: bool = True
    remarks: Optional[str] = None
    created_at: Optional[datetime] = None

class BreakStatusResponse(BaseModel):
    is_on_break: bool = False
    current_break: Optional[BreakSessionResponse] = None
    total_break_minutes: int = 0
    paid_break_minutes: int = 0
    unpaid_break_minutes: int = 0
    breaks_taken_count: int = 0
