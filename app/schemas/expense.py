from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

class ExpenseClaimBase(BaseModel):
    title: str = Field(..., max_length=200)
    category: str = Field(..., max_length=50)
    amount: Decimal = Field(..., gt=0)
    expense_date: date
    notes: Optional[str] = None
    receipt_name: Optional[str] = None

class ExpenseClaimCreate(ExpenseClaimBase):
    pass

class ExpenseClaimReview(BaseModel):
    status: str = Field(..., pattern="^(APPROVED|REJECTED)$")
    approved_amount: Optional[Decimal] = None
    remarks: Optional[str] = None

class ExpenseClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    employee_name: str
    employee_code: str
    department: str
    title: str
    category: str
    amount: float
    approved_amount: Optional[float] = None
    expense_date: str
    status: str
    notes: Optional[str] = None
    receipt_name: Optional[str] = None
    reviewer_remarks: Optional[str] = None
    created_at: str

class ExpenseListResponse(BaseModel):
    items: List[ExpenseClaimResponse]
    total: int
    total_amount: float
    approved_amount: float
    pending_amount: float
