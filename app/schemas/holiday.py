from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class HolidayCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    date: date
    description: Optional[str] = None
    is_optional: bool = False

class HolidayUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    date: Optional[date] = None
    description: Optional[str] = None
    is_optional: Optional[bool] = None

class HolidayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    date: date
    description: Optional[str] = None
    is_optional: bool
    created_at: Optional[datetime] = None
