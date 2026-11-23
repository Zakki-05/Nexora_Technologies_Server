from datetime import date, datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.attendance import EmployeeShortInfo

# ==================== LEAVE TYPE SCHEMAS ====================

class LeaveTypeCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=30)
    description: Optional[str] = Field(None, max_length=255)
    annual_allocation: int = Field(0, ge=0)
    is_paid: bool = True
    carry_forward_enabled: bool = False
    max_carry_forward_days: int = Field(0, ge=0)
    max_consecutive_days: int = Field(15, ge=1)
    requires_document: bool = False
    allow_half_day: bool = True
    is_active: bool = True

class LeaveTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    code: Optional[str] = Field(None, min_length=2, max_length=30)
    description: Optional[str] = Field(None, max_length=255)
    annual_allocation: Optional[int] = Field(None, ge=0)
    is_paid: Optional[bool] = None
    carry_forward_enabled: Optional[bool] = None
    max_carry_forward_days: Optional[int] = Field(None, ge=0)
    max_consecutive_days: Optional[int] = Field(None, ge=1)
    requires_document: Optional[bool] = None
    allow_half_day: Optional[bool] = None
    is_active: Optional[bool] = None

class LeaveTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    description: Optional[str] = None
    annual_allocation: int
    is_paid: bool
    carry_forward_enabled: bool
    max_carry_forward_days: int
    max_consecutive_days: int
    requires_document: bool
    allow_half_day: bool
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# ==================== LEAVE APPLICATION & REVIEW SCHEMAS ====================

class LeaveCreate(BaseModel):
    leave_type: str = "Annual"
    leave_type_id: Optional[int] = None
    start_date: date
    end_date: date
    reason: str = Field(min_length=3, max_length=500)
    is_half_day: bool = False
    half_day_session: Optional[Literal["FIRST_HALF", "SECOND_HALF"]] = None
    exclude_weekends: Optional[bool] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.is_half_day:
            if not self.half_day_session:
                self.half_day_session = "FIRST_HALF"
            self.end_date = self.start_date
        elif self.end_date < self.start_date:
            raise ValueError("End date cannot be earlier than start date")
        return self

class LeaveDecision(BaseModel):
    status: Literal["APPROVED", "REJECTED", "ACCEPTED"]
    rejection_reason: Optional[str] = None

    @model_validator(mode="after")
    def normalize_and_validate(self):
        if self.status == "ACCEPTED":
            self.status = "APPROVED"
        if self.status == "REJECTED" and not self.rejection_reason:
            raise ValueError("Rejection reason is required when rejecting a leave request")
        return self

class ApproverInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str

class LeaveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    leave_type_id: Optional[int] = None
    leave_type: str
    start_date: date
    end_date: date
    days_count: float
    is_half_day: bool = False
    half_day_session: Optional[str] = None
    reason: Optional[str] = None
    status: str
    approved_by: Optional[int] = None
    rejection_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    employee: Optional[EmployeeShortInfo] = None
    approver: Optional[ApproverInfo] = None

# ==================== LEDGER & BALANCE SCHEMAS ====================

class LeaveTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    leave_type_id: int
    leave_type_name: Optional[str] = None
    leave_type_code: Optional[str] = None
    transaction_type: str
    days: float
    reference_id: str
    balance_after: float
    remarks: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None

class LeaveTypeBalanceDetail(BaseModel):
    leave_type_id: int
    leave_type_name: str
    leave_type_code: str
    annual_allocation: float
    carried_forward: float
    manual_adjustments: float
    approved_consumed: float
    pending_reserved: float
    settled_balance: float = 0.0
    available: float
    is_paid: bool

class LeaveBalanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    year: int
    annual_total: int
    annual_used: int
    annual_remaining: int = 0

    sick_total: int
    sick_used: int
    sick_remaining: int = 0

    casual_total: int
    casual_used: int
    casual_remaining: int = 0

    unpaid_used: int
    pending_reserved: int = 0
    carried_forward: int = 0
    available_total: int = 0

    type_balances: List[LeaveTypeBalanceDetail] = []

class LeaveBalanceUpdate(BaseModel):
    annual_total: Optional[int] = Field(None, ge=0)
    sick_total: Optional[int] = Field(None, ge=0)
    casual_total: Optional[int] = Field(None, ge=0)

class LeaveAdjustmentRequest(BaseModel):
    employee_id: int
    leave_type_id: int
    adjustment_days: float
    remarks: str = Field(..., min_length=3, max_length=255)
