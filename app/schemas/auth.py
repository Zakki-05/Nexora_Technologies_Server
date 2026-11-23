from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict, Field

class UserRegister(BaseModel):
    username: Optional[str] = Field(default=None, min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6, max_length=100)
    role: str = Field(default="EMPLOYEE")

UserCreate = UserRegister

class UserLogin(BaseModel):
    email: str # Can be username or email address
    password: str

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=100)

class UserStatusUpdate(BaseModel):
    is_active: bool

class UserRoleUpdate(BaseModel):
    role: str

class EmployeeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_code: str
    full_name: str
    phone: str
    position: str
    department_id: Optional[int] = None
    employment_status: str
    profile_picture: Optional[str] = None
    pending_profile_picture: Optional[str] = None
    profile_picture_status: Optional[str] = "APPROVED"
    profile_picture_rejection_reason: Optional[str] = None

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: Optional[datetime] = None
    employee: Optional[EmployeeSummary] = None

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Optional[UserResponse] = None

class TokenData(BaseModel):
    user_id: Optional[int] = None
    role: Optional[str] = None
