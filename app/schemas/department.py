from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class DepartmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None

class DepartmentUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None

class DepartmentReassign(BaseModel):
    target_department_id: int = Field(gt=0)

class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    employee_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
