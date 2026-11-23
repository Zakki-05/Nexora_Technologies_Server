from datetime import time, datetime
from sqlalchemy import String, Integer, Time, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class AttendancePolicy(Base):
    __tablename__ = "attendance_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    policy_name: Mapped[str] = mapped_column(String(100), default="Standard Corporate Policy", nullable=False)
    office_start_time: Mapped[time] = mapped_column(Time, default=time(9, 0), nullable=False)
    office_end_time: Mapped[time] = mapped_column(Time, default=time(18, 0), nullable=False)
    grace_period_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    late_threshold_time: Mapped[time] = mapped_column(Time, default=time(9, 30), nullable=False)
    full_day_minutes: Mapped[int] = mapped_column(Integer, default=480, nullable=False)
    half_day_minutes: Mapped[int] = mapped_column(Integer, default=240, nullable=False)
    max_daily_break_minutes: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    max_tea_break_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    max_lunch_break_minutes: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    max_personal_break_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    paid_break_types: Mapped[str] = mapped_column(String(255), default="TEA_BREAK,SHORT_BREAK", nullable=False)
    unpaid_break_types: Mapped[str] = mapped_column(String(255), default="LUNCH_BREAK,PERSONAL_BREAK,OTHER_BREAK", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
