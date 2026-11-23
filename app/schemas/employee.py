from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Optional, Literal
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, StringConstraints

PhoneNumber = Annotated[str, StringConstraints(min_length=10, max_length=20)]

class EmployeeBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    phone: PhoneNumber = Field(
        validation_alias=AliasChoices("phone", "phone_number")
    )
    hire_date: date
    position: str
    salary: Decimal = Field(gt=0)
    department_id: int = Field(gt=0)
    employee_code: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    address: Optional[str] = None
    profile_picture: Optional[str] = None
    employment_status: str = Field(default="ACTIVE")

class EmployeeCreate(EmployeeBase):
    user_id: Optional[int] = Field(default=None, gt=0)
    email: Optional[str] = None
    password: Optional[str] = None
    username: Optional[str] = None

class EmployeeUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    phone: PhoneNumber = Field(
        validation_alias=AliasChoices("phone", "phone_number")
    )
    hire_date: date
    position: str
    salary: Decimal = Field(gt=0)
    department_id: int = Field(gt=0)
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    address: Optional[str] = None
    profile_picture: Optional[str] = None
    employment_status: Optional[str] = "ACTIVE"

class EmployeePatch(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    phone: Optional[PhoneNumber] = Field(
        default=None,
        validation_alias=AliasChoices("phone", "phone_number"),
    )
    hire_date: Optional[date] = None
    position: Optional[str] = None
    salary: Optional[Decimal] = Field(default=None, gt=0)
    department_id: Optional[int] = Field(default=None, gt=0)
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    address: Optional[str] = None
    profile_picture: Optional[str] = None
    employment_status: Optional[str] = None

class EmployeeSelfUpdate(BaseModel):
    phone: Optional[PhoneNumber] = Field(
        default=None,
        validation_alias=AliasChoices("phone", "phone_number"),
    )
    address: Optional[str] = None
    profile_picture: Optional[str] = None

class EmployeeStatusUpdate(BaseModel):
    employment_status: str

class DepartmentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str

class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str
    role: str
    is_active: bool

class LeaveBalanceBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    annual_total: int
    annual_used: int
    sick_total: int
    sick_used: int
    casual_total: int
    casual_used: int
    unpaid_used: int

class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_code: str
    full_name: str
    phone: str
    hire_date: date
    position: str
    salary: Decimal
    department_id: int
    user_id: int
    email: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    address: Optional[str] = None
    profile_picture: Optional[str] = None
    pending_profile_picture: Optional[str] = None
    profile_picture_status: Optional[str] = "APPROVED"
    profile_picture_rejection_reason: Optional[str] = None
    profile_picture_updated_at: Optional[datetime] = None
    employment_status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    department: Optional[DepartmentBrief] = None
    user: Optional[UserBrief] = None
    leave_balance: Optional[LeaveBalanceBrief] = None

class AvatarReviewRequest(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    rejection_reason: Optional[str] = None

class AvatarPendingRequestResponse(BaseModel):
    employee_id: int
    employee_code: str
    full_name: str
    department_name: Optional[str] = None
    current_avatar: Optional[str] = None
    current_profile_picture: Optional[str] = None
    pending_avatar: str
    pending_profile_picture: Optional[str] = None
    status: str = "PENDING"
    profile_picture_status: Optional[str] = "PENDING"
    submitted_at: Optional[datetime] = None
