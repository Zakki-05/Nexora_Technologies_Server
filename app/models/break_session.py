from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class BreakSession(Base):
    __tablename__ = "break_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    attendance_id: Mapped[int] = mapped_column(Integer, ForeignKey("attendances.id"), index=True, nullable=False)
    session_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("attendance_sessions.id"), index=True, nullable=True)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    break_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    break_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    break_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    attendance = relationship("Attendance", back_populates="breaks")
    session = relationship("AttendanceSession", back_populates="breaks")
    employee = relationship("Employee", back_populates="break_sessions")
