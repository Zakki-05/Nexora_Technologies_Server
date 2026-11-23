from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class LeaveTransaction(Base):
    __tablename__ = "leave_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    leave_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("leave_types.id"), index=True, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    days: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    employee = relationship("Employee", back_populates="leave_transactions")
    leave_type = relationship("LeaveType", back_populates="transactions")
    creator = relationship("User", foreign_keys=[created_by])
