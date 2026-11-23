from datetime import date, time, datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Date, DateTime, ForeignKey, Time, Numeric, Boolean, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class Attendance(Base):
    __tablename__ = "attendances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    check_in: Mapped[time | None] = mapped_column(Time, nullable=True)
    check_out: Mapped[time | None] = mapped_column(Time, nullable=True)
    work_hours: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=0.0, nullable=False)

    @property
    def working_hours(self) -> Decimal:
        return self.work_hours

    @property
    def is_punched_in(self) -> bool:
        if self.sessions:
            return any(s.punch_out is None for s in self.sessions)
        return self.check_in is not None and self.check_out is None

    office_duration_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    actual_working_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_break_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paid_break_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unpaid_break_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_late: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_incomplete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PRESENT", index=True, nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_attendance_employee_date"),
    )

    employee = relationship("Employee", foreign_keys=[employee_id], back_populates="attendances")
    sessions = relationship("AttendanceSession", back_populates="attendance", cascade="all, delete-orphan", order_by="AttendanceSession.id")
    breaks = relationship("BreakSession", back_populates="attendance", cascade="all, delete-orphan", order_by="BreakSession.id")
    corrections = relationship("AttendanceCorrection", back_populates="attendance", cascade="all, delete-orphan")
