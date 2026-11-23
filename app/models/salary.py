from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Date, DateTime, Boolean, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class Salary(Base):
    __tablename__ = "salaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    basic_salary: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    hra: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    da: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    conveyance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    medical: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    special_allowance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    bonus: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    overtime_pay: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    allowances: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)

    pf_deduction: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    professional_tax: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    tds_deduction: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    esi_deduction: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    loss_of_pay: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    lop_days: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=0.0, nullable=False)
    deductions: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)

    net_salary: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PAID", index=True, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), default="BANK_TRANSFER", nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    employee = relationship("Employee", back_populates="salaries")
