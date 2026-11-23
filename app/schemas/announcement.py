from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, ConfigDict, Field

class AnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=150)
    message: str = Field(..., min_length=3)
    priority: Literal["URGENT", "HIGH", "NORMAL"] = "NORMAL"
    target_type: Literal["ALL", "DEPARTMENT", "ROLE"] = "ALL"
    target_department_id: Optional[int] = None
    target_role: Optional[Literal["EMPLOYEE", "ADMIN", "SUPER_ADMIN"]] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True
    broadcast_notification: bool = True

class AnnouncementUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=150)
    message: Optional[str] = Field(None, min_length=3)
    priority: Optional[Literal["URGENT", "HIGH", "NORMAL"]] = None
    target_type: Optional[Literal["ALL", "DEPARTMENT", "ROLE"]] = None
    target_department_id: Optional[int] = None
    target_role: Optional[Literal["EMPLOYEE", "ADMIN", "SUPER_ADMIN"]] = None
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None

class AnnouncementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    message: str
    priority: str
    target_type: str
    target_department_id: Optional[int] = None
    target_department_name: Optional[str] = None
    target_role: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_active: bool
    created_by: int
    author_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
