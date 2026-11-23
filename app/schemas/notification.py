from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class NotificationCreate(BaseModel):
    user_id: int = Field(gt=0)
    title: str = Field(min_length=2, max_length=150)
    message: str = Field(min_length=2)
    type: str = Field(default="GENERAL")

class NotificationBroadcast(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    message: str = Field(min_length=2)
    type: str = Field(default="ANNOUNCEMENT")
    target_role: Optional[str] = None

class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    message: str
    type: str
    is_read: bool
    created_at: Optional[datetime] = None

class UnreadCountResponse(BaseModel):
    unread_count: int
