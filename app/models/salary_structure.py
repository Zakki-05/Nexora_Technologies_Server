from datetime import datetime
from decimal import Decimal
from sqlalchemy import Integer, Numeric, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class SalaryStructure(Base):
    __tablename__ = "salary_structures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id"), unique=True, index=True, nullable=False)
    basic_salary: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    hra: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    da: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    conveyance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    medical_allowance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    special_allowance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    pf_deduction_rate: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=12.0, nullable=False)
    professional_tax: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=200.0, nullable=False)
    esi_rate: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=0.75, nullable=False)
    tds_rate: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=0.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    employee = relationship("Employee", back_populates="salary_structure")
