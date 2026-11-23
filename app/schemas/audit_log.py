from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.employee import UserBrief

class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: Optional[datetime] = None
    user: Optional[UserBrief] = None
