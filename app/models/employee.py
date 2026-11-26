from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Date, DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id"), default=1, index=True, nullable=False)
    employee_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column("name", String(100), index=True, nullable=False)
    phone: Mapped[str] = mapped_column("phone_number", String(20), unique=True, nullable=False)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    position: Mapped[str] = mapped_column(String(100), nullable=False)
    salary: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    department_id: Mapped[int] = mapped_column(Integer, ForeignKey("departments.id"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, index=True, nullable=False)

    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_picture: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pending_profile_picture: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_picture_status: Mapped[str | None] = mapped_column(String(30), default="APPROVED", nullable=True)
    profile_picture_rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_picture_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    employment_status: Mapped[str] = mapped_column(String(30), default="ACTIVE", index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    @property
    def email(self) -> str | None:
        return self.user.email if self.user else None

    user = relationship("User", back_populates="employee")
    organization = relationship("Organization", back_populates="employees")
    department = relationship("Department", back_populates="employees")
    leaves = relationship("Leave", foreign_keys="Leave.employee_id", back_populates="employee", cascade="all, delete-orphan")
    attendances = relationship("Attendance", back_populates="employee", cascade="all, delete-orphan")
    attendance_sessions = relationship("AttendanceSession", back_populates="employee", cascade="all, delete-orphan")
    break_sessions = relationship("BreakSession", back_populates="employee", cascade="all, delete-orphan")
    leave_balance = relationship("LeaveBalance", back_populates="employee", uselist=False, cascade="all, delete-orphan")
    leave_transactions = relationship("LeaveTransaction", back_populates="employee", cascade="all, delete-orphan")
    salaries = relationship("Salary", back_populates="employee", cascade="all, delete-orphan")
    salary_structure = relationship("SalaryStructure", back_populates="employee", uselist=False, cascade="all, delete-orphan")
    documents = relationship("EmployeeDocument", back_populates="employee", cascade="all, delete-orphan")
    expense_claims = relationship("ExpenseClaim", back_populates="employee", cascade="all, delete-orphan")
