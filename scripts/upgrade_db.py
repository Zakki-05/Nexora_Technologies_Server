import os
import sys
from datetime import time
from decimal import Decimal
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base, engine, SessionLocal
from app.models import (
    User, Employee, Department, Attendance, AttendanceSession, BreakSession,
    AttendancePolicy, AttendanceCorrection, Leave, LeaveType, LeaveBalance,
    LeaveTransaction, Holiday, Salary, SalaryStructure, Notification,
    Announcement, AuditLog, EmployeeDocument
)

def run_db_upgrade():
    print("[1/5] Creating any new tables in database...")
    Base.metadata.create_all(bind=engine)
    print("      New tables verified/created successfully.")

    db = SessionLocal()
    try:
        print("[2/5] Checking and adding missing columns to existing tables...")
        # Inspect columns for attendances
        dialect = engine.dialect.name
        
        attendance_cols = [
            ("office_duration_minutes", "INTEGER DEFAULT 0"),
            ("actual_working_minutes", "INTEGER DEFAULT 0"),
            ("total_break_minutes", "INTEGER DEFAULT 0"),
            ("paid_break_minutes", "INTEGER DEFAULT 0"),
            ("unpaid_break_minutes", "INTEGER DEFAULT 0"),
            ("overtime_minutes", "INTEGER DEFAULT 0"),
            ("is_incomplete", "BOOLEAN DEFAULT 0" if dialect == "sqlite" else "BOOLEAN DEFAULT FALSE"),
        ]
        for col_name, col_def in attendance_cols:
            try:
                db.execute(text(f"ALTER TABLE attendances ADD COLUMN {col_name} {col_def};"))
                db.commit()
                print(f"      Added column {col_name} to attendances")
            except Exception:
                db.rollback()

        # Inspect columns for leaves
        leave_cols = [
            ("leave_type_id", "INTEGER REFERENCES leave_types(id)" if dialect != "sqlite" else "INTEGER"),
            ("is_half_day", "BOOLEAN DEFAULT 0" if dialect == "sqlite" else "BOOLEAN DEFAULT FALSE"),
            ("half_day_session", "VARCHAR(20)"),
        ]
        for col_name, col_def in leave_cols:
            try:
                db.execute(text(f"ALTER TABLE leaves ADD COLUMN {col_name} {col_def};"))
                db.commit()
                print(f"      Added column {col_name} to leaves")
            except Exception:
                db.rollback()

        # Inspect columns for leave_balances
        bal_cols = [
            ("pending_reserved", "INTEGER DEFAULT 0"),
            ("carried_forward", "INTEGER DEFAULT 0"),
            ("leave_type_id", "INTEGER REFERENCES leave_types(id)" if dialect != "sqlite" else "INTEGER"),
        ]
        for col_name, col_def in bal_cols:
            try:
                db.execute(text(f"ALTER TABLE leave_balances ADD COLUMN {col_name} {col_def};"))
                db.commit()
                print(f"      Added column {col_name} to leave_balances")
            except Exception:
                db.rollback()

        # Inspect columns for salaries
        salary_cols = [
            ("month", "INTEGER"),
            ("year", "INTEGER"),
            ("hra", "NUMERIC(10, 2) DEFAULT 0.0"),
            ("da", "NUMERIC(10, 2) DEFAULT 0.0"),
            ("conveyance", "NUMERIC(10, 2) DEFAULT 0.0"),
            ("medical", "NUMERIC(10, 2) DEFAULT 0.0"),
            ("special_allowance", "NUMERIC(10, 2) DEFAULT 0.0"),
            ("bonus", "NUMERIC(10, 2) DEFAULT 0.0"),
            ("overtime_pay", "NUMERIC(10, 2) DEFAULT 0.0"),
            ("pf_deduction", "NUMERIC(10, 2) DEFAULT 0.0"),
            ("professional_tax", "NUMERIC(10, 2) DEFAULT 0.0"),
            ("tds_deduction", "NUMERIC(10, 2) DEFAULT 0.0"),
            ("esi_deduction", "NUMERIC(10, 2) DEFAULT 0.0"),
            ("loss_of_pay", "NUMERIC(10, 2) DEFAULT 0.0"),
            ("lop_days", "NUMERIC(4, 1) DEFAULT 0.0"),
            ("is_locked", "BOOLEAN DEFAULT 0" if dialect == "sqlite" else "BOOLEAN DEFAULT FALSE"),
        ]
        for col_name, col_def in salary_cols:
            try:
                db.execute(text(f"ALTER TABLE salaries ADD COLUMN {col_name} {col_def};"))
                db.commit()
                print(f"      Added column {col_name} to salaries")
            except Exception:
                db.rollback()

        print("[3/5] Seeding standard 10 Enterprise Leave Types...")
        standard_types = [
            ("Annual Leave", "ANNUAL_LEAVE", "Paid vacation leave", 18, True, True, 10, 15, False, True),
            ("Sick Leave", "SICK_LEAVE", "Medical and health related absence", 12, True, False, 0, 7, True, True),
            ("Casual Leave", "CASUAL_LEAVE", "Unforeseen personal affairs", 10, True, False, 0, 3, False, True),
            ("Unpaid Leave", "UNPAID_LEAVE", "Leave without pay / Loss of Pay", 0, False, False, 0, 30, False, True),
            ("Maternity Leave", "MATERNITY_LEAVE", "Statutory maternity benefit", 180, True, False, 0, 180, True, False),
            ("Paternity Leave", "PATERNITY_LEAVE", "Parental leave for fathers", 15, True, False, 0, 15, False, False),
            ("Compensatory Off", "COMPENSATORY_OFF", "Credit for working on holidays/weekends", 0, True, True, 5, 2, False, True),
            ("Bereavement Leave", "BEREAVEMENT_LEAVE", "Leave for immediate family bereavement", 5, True, False, 0, 5, False, False),
            ("Marriage Leave", "MARRIAGE_LEAVE", "Special celebration leave for wedding", 5, True, False, 0, 5, False, False),
            ("Optional Holiday", "OPTIONAL_HOLIDAY", "Floating holiday from company list", 2, True, False, 0, 1, False, False),
        ]
        for name, code, desc, alloc, is_paid, cf, max_cf, max_cons, req_doc, half_d in standard_types:
            lt = db.query(LeaveType).filter(LeaveType.code == code).first()
            if not lt:
                lt = LeaveType(
                    name=name,
                    code=code,
                    description=desc,
                    annual_allocation=alloc,
                    is_paid=is_paid,
                    carry_forward_enabled=cf,
                    max_carry_forward_days=max_cf,
                    max_consecutive_days=max_cons,
                    requires_document=req_doc,
                    allow_half_day=half_d,
                    is_active=True
                )
                db.add(lt)
                db.commit()
                print(f"      Created LeaveType: {code} ({name})")

        print("[4/5] Seeding Default Attendance Policy...")
        policy = db.query(AttendancePolicy).first()
        if not policy:
            policy = AttendancePolicy(
                policy_name="WorkPulse Standard Corporate Policy",
                office_start_time=time(9, 0),
                office_end_time=time(18, 0),
                grace_period_minutes=30,
                late_threshold_time=time(9, 30),
                full_day_minutes=480,
                half_day_minutes=240,
                max_daily_break_minutes=90,
                max_tea_break_minutes=15,
                max_lunch_break_minutes=45,
                max_personal_break_minutes=15,
                paid_break_types="TEA_BREAK,SHORT_BREAK",
                unpaid_break_types="LUNCH_BREAK,PERSONAL_BREAK,OTHER_BREAK",
                is_active=True
            )
            db.add(policy)
            db.commit()
            print("      Created default AttendancePolicy.")

        print("[5/5] Provisioning SalaryStructures for existing employees...")
        employees = db.query(Employee).all()
        for emp in employees:
            struct = db.query(SalaryStructure).filter(SalaryStructure.employee_id == emp.id).first()
            if not struct:
                base = emp.salary
                struct = SalaryStructure(
                    employee_id=emp.id,
                    basic_salary=Decimal(str(round(float(base) * 0.50, 2))),
                    hra=Decimal(str(round(float(base) * 0.25, 2))),
                    da=Decimal(str(round(float(base) * 0.10, 2))),
                    conveyance=Decimal("2000.00"),
                    medical_allowance=Decimal("1500.00"),
                    special_allowance=Decimal(str(max(0.0, round(float(base) * 0.15 - 3500.0, 2)))),
                    pf_deduction_rate=Decimal("12.00"),
                    professional_tax=Decimal("200.00"),
                    esi_rate=Decimal("0.75"),
                    tds_rate=Decimal("0.00"),
                    is_active=True
                )
                db.add(struct)
                db.commit()
                print(f"      Provisioned SalaryStructure for {emp.full_name} ({emp.employee_code})")

        print("=== Database Upgrade Complete! ===")
    except Exception as e:
        db.rollback()
        print(f"Error during database upgrade: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    run_db_upgrade()
