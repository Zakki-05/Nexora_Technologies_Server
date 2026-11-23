from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Literal, List
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.attendance import EmployeeShortInfo

# ==================== SALARY STRUCTURE SCHEMAS ====================

class SalaryStructureCreate(BaseModel):
    employee_id: int = Field(gt=0)
    basic_salary: Decimal = Field(gt=0, description="Monthly basic salary in INR")
    hra: Decimal = Field(default=Decimal("0.00"), ge=0, description="House Rent Allowance")
    da: Decimal = Field(default=Decimal("0.00"), ge=0, description="Dearness Allowance")
    conveyance: Decimal = Field(default=Decimal("0.00"), ge=0, description="Conveyance Allowance")
    medical_allowance: Decimal = Field(default=Decimal("0.00"), ge=0, description="Medical Allowance")
    special_allowance: Decimal = Field(default=Decimal("0.00"), ge=0, description="Special / Flexible Allowance")
    pf_deduction_rate: Decimal = Field(default=Decimal("12.00"), ge=0, le=100, description="EPF deduction percentage")
    professional_tax: Decimal = Field(default=Decimal("200.00"), ge=0, description="Monthly PT in INR")
    esi_rate: Decimal = Field(default=Decimal("0.75"), ge=0, le=100, description="ESIC employee percentage")
    tds_rate: Decimal = Field(default=Decimal("0.00"), ge=0, le=100, description="Monthly TDS deduction rate")
    is_active: bool = True

class SalaryStructureUpdate(BaseModel):
    basic_salary: Optional[Decimal] = Field(None, gt=0)
    hra: Optional[Decimal] = Field(None, ge=0)
    da: Optional[Decimal] = Field(None, ge=0)
    conveyance: Optional[Decimal] = Field(None, ge=0)
    medical_allowance: Optional[Decimal] = Field(None, ge=0)
    special_allowance: Optional[Decimal] = Field(None, ge=0)
    pf_deduction_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    professional_tax: Optional[Decimal] = Field(None, ge=0)
    esi_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    tds_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None

class SalaryStructureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    basic_salary: Decimal
    hra: Decimal
    da: Decimal
    conveyance: Decimal
    medical_allowance: Decimal
    special_allowance: Decimal
    gross_monthly: Decimal
    pf_deduction_rate: Decimal
    professional_tax: Decimal
    esi_rate: Decimal
    tds_rate: Decimal
    is_active: bool
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class SalaryStructurePreviewRequest(BaseModel):
    annual_ctc: Decimal = Field(gt=0, description="Total annual Cost-to-Company in INR")
    basic_percentage: Decimal = Field(default=Decimal("50.00"), ge=30, le=70, description="Percentage of CTC for Basic")
    hra_percentage: Decimal = Field(default=Decimal("40.00"), ge=0, le=50, description="Percentage of Basic for HRA")
    conveyance_monthly: Decimal = Field(default=Decimal("1600.00"), ge=0)
    medical_monthly: Decimal = Field(default=Decimal("1250.00"), ge=0)
    pf_deduction_rate: Decimal = Field(default=Decimal("12.00"), ge=0, le=100)
    professional_tax: Decimal = Field(default=Decimal("200.00"), ge=0)
    esi_rate: Decimal = Field(default=Decimal("0.75"), ge=0, le=100)
    tds_rate: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)

class SalaryStructurePreviewResponse(BaseModel):
    annual_ctc: Decimal
    monthly_ctc: Decimal
    basic_salary: Decimal
    hra: Decimal
    da: Decimal
    conveyance: Decimal
    medical_allowance: Decimal
    special_allowance: Decimal
    gross_monthly: Decimal
    pf_monthly: Decimal
    professional_tax: Decimal
    esi_monthly: Decimal
    tds_monthly: Decimal
    total_deductions: Decimal
    net_take_home: Decimal

# ==================== SALARY RECORD SCHEMAS ====================

class SalaryCreate(BaseModel):
    employee_id: int = Field(gt=0)
    month: Optional[int] = Field(None, ge=1, le=12)
    year: Optional[int] = Field(None, ge=2020, le=2100)
    basic_salary: Decimal = Field(gt=0)
    hra: Decimal = Field(default=Decimal("0.00"), ge=0)
    da: Decimal = Field(default=Decimal("0.00"), ge=0)
    conveyance: Decimal = Field(default=Decimal("0.00"), ge=0)
    medical: Decimal = Field(default=Decimal("0.00"), ge=0)
    special_allowance: Decimal = Field(default=Decimal("0.00"), ge=0)
    bonus: Decimal = Field(default=Decimal("0.00"), ge=0)
    overtime_pay: Decimal = Field(default=Decimal("0.00"), ge=0)
    allowances: Decimal = Field(default=Decimal("0.00"), ge=0)

    pf_deduction: Decimal = Field(default=Decimal("0.00"), ge=0)
    professional_tax: Decimal = Field(default=Decimal("0.00"), ge=0)
    tds_deduction: Decimal = Field(default=Decimal("0.00"), ge=0)
    esi_deduction: Decimal = Field(default=Decimal("0.00"), ge=0)
    loss_of_pay: Decimal = Field(default=Decimal("0.00"), ge=0)
    lop_days: Decimal = Field(default=Decimal("0.0"), ge=0)
    deductions: Decimal = Field(default=Decimal("0.00"), ge=0)

    payment_date: date
    status: Literal["PAID", "PENDING"] = "PAID"
    payment_method: Literal["BANK_TRANSFER", "CASH", "CHEQUE"] = "BANK_TRANSFER"
    notes: Optional[str] = None

class SalaryUpdate(BaseModel):
    basic_salary: Optional[Decimal] = Field(None, gt=0)
    hra: Optional[Decimal] = Field(None, ge=0)
    da: Optional[Decimal] = Field(None, ge=0)
    conveyance: Optional[Decimal] = Field(None, ge=0)
    medical: Optional[Decimal] = Field(None, ge=0)
    special_allowance: Optional[Decimal] = Field(None, ge=0)
    bonus: Optional[Decimal] = Field(None, ge=0)
    overtime_pay: Optional[Decimal] = Field(None, ge=0)
    allowances: Optional[Decimal] = Field(None, ge=0)

    pf_deduction: Optional[Decimal] = Field(None, ge=0)
    professional_tax: Optional[Decimal] = Field(None, ge=0)
    tds_deduction: Optional[Decimal] = Field(None, ge=0)
    esi_deduction: Optional[Decimal] = Field(None, ge=0)
    loss_of_pay: Optional[Decimal] = Field(None, ge=0)
    lop_days: Optional[Decimal] = Field(None, ge=0)
    deductions: Optional[Decimal] = Field(None, ge=0)

    payment_date: Optional[date] = None
    status: Optional[Literal["PAID", "PENDING"]] = None
    payment_method: Optional[Literal["BANK_TRANSFER", "CASH", "CHEQUE"]] = None
    notes: Optional[str] = None

class SalaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    month: Optional[int] = None
    year: Optional[int] = None
    basic_salary: Decimal
    hra: Decimal = Decimal("0.00")
    da: Decimal = Decimal("0.00")
    conveyance: Decimal = Decimal("0.00")
    medical: Decimal = Decimal("0.00")
    special_allowance: Decimal = Decimal("0.00")
    bonus: Decimal = Decimal("0.00")
    overtime_pay: Decimal = Decimal("0.00")
    allowances: Decimal
    gross_earnings: Decimal = Decimal("0.00")

    pf_deduction: Decimal = Decimal("0.00")
    professional_tax: Decimal = Decimal("0.00")
    tds_deduction: Decimal = Decimal("0.00")
    esi_deduction: Decimal = Decimal("0.00")
    loss_of_pay: Decimal = Decimal("0.00")
    lop_days: Decimal = Decimal("0.0")
    deductions: Decimal

    net_salary: Decimal
    payment_date: date
    status: str
    payment_method: str
    is_locked: bool = False
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    employee: Optional[EmployeeShortInfo] = None

class SalarySummary(BaseModel):
    total_payroll: Decimal = Decimal("0.00")
    total_paid: Decimal = Decimal("0.00")
    total_pending: Decimal = Decimal("0.00")
    record_count: int = 0

# ==================== PAYROLL RUN SCHEMAS ====================

class PayrollRunRequest(BaseModel):
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2020, le=2100)
    department_id: Optional[int] = None
    employee_id: Optional[int] = None
    action: Literal["PREVIEW", "PROCESS", "LOCK"] = "PROCESS"
    payment_method: Literal["BANK_TRANSFER", "CASH", "CHEQUE"] = "BANK_TRANSFER"
    payment_date: Optional[date] = None

class PayrollRunItem(BaseModel):
    employee_id: int
    employee_code: str
    employee_name: str
    department_name: str
    basic_salary: Decimal
    gross_earnings: Decimal
    pf_deduction: Decimal
    professional_tax: Decimal
    esi_deduction: Decimal
    tds_deduction: Decimal
    lop_days: Decimal
    loss_of_pay: Decimal
    total_deductions: Decimal
    net_salary: Decimal
    status: str
    is_locked: bool

class PayrollRunResponse(BaseModel):
    month: int
    year: int
    action: str
    total_employees: int
    total_gross: Decimal
    total_deductions: Decimal
    total_net_payout: Decimal
    items: List[PayrollRunItem]
    message: str
