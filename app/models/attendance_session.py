from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    attendance_id: Mapped[int] = mapped_column(Integer, ForeignKey("attendances.id"), index=True, nullable=False)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    session_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    punch_in: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    punch_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    attendance = relationship("Attendance", back_populates="sessions")
    employee = relationship("Employee", back_populates="attendance_sessions")
    breaks = relationship("BreakSession", back_populates="session", cascade="all, delete-orphan")
