from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class OrganizationBase(BaseModel):
    name: str
    slug: str
    company_code: str
    contact_email: Optional[str] = None
    timezone: str = "Asia/Kolkata"
    subscription_plan: str = "ENTERPRISE"

class OrganizationResponse(OrganizationBase):
    id: int
    is_active: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
