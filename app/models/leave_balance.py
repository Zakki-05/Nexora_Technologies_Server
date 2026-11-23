from datetime import datetime
from sqlalchemy import Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class LeaveBalance(Base):
    __tablename__ = "leave_balances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id"), unique=True, index=True, nullable=False)
    year: Mapped[int] = mapped_column(Integer, default=datetime.now().year, nullable=False)

    annual_total: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    annual_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    sick_total: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    sick_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    casual_total: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    casual_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    unpaid_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    pending_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    carried_forward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leave_type_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("leave_types.id"), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    employee = relationship("Employee", back_populates="leave_balance")
    leave_type = relationship("LeaveType", foreign_keys=[leave_type_id])
