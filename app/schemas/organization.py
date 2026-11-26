from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class OrganizationBase(BaseModel):
    name: str
    slug: str
    company_code: str
    contact_email: Optional[str] = None
    timezone: str = "Asia/Kolkata"
    subscription_plan: str = "ENTERPRISE"

class OrganizationResponse(OrganizationBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    created_at: Optional[datetime] = None
