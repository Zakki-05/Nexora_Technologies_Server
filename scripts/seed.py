import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base, engine, SessionLocal
from app.models.user import User
from app.models.department import Department
from app.models.employee import Employee
from app.models.leave_balance import LeaveBalance
from app.models.holiday import Holiday
from app.models.salary import Salary
from app.utils.security import hash_password

def seed_database():
    print("Creating all tables in database...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 1. Seed Super Admin
        super_admin = db.query(User).filter(User.email == "superadmin@ems.com").first()
        if not super_admin:
            super_admin = User(
                username="superadmin",
                email="superadmin@ems.com",
                hashed_password=hash_password("Admin@123"),
                role="SUPER_ADMIN",
                is_active=True
            )
            db.add(super_admin)
            db.commit()
            db.refresh(super_admin)
            print("Created Super Admin user: superadmin@ems.com / Admin@123")
        else:
            print("Super Admin already exists.")

        # 2. Seed Admin
        admin_user = db.query(User).filter(User.email == "admin@ems.com").first()
        if not admin_user:
            admin_user = User(
                username="admin",
                email="admin@ems.com",
                hashed_password=hash_password("Admin@123"),
                role="ADMIN",
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            print("Created Admin user: admin@ems.com / Admin@123")

        # 3. Seed Departments
        dept_names = [
            ("Engineering", "Software development, QA, and platform infrastructure"),
            ("Human Resources", "Talent acquisition, employee welfare, and HR policies"),
            ("Finance", "Payroll, accounting, financial planning and analysis"),
            ("Marketing", "Brand marketing, growth strategies, and communications"),
            ("Operations", "Office management, procurement, and daily operations"),
        ]
        departments = {}
        for name, desc in dept_names:
            dept = db.query(Department).filter(Department.name == name).first()
            if not dept:
                dept = Department(name=name, description=desc)
                db.add(dept)
                db.commit()
                db.refresh(dept)
                print(f"Created department: {name}")
            departments[name] = dept

        # 3b. Provision Employee for Super Admin if missing
        if super_admin and not super_admin.employee:
            super_emp = Employee(
                user_id=super_admin.id,
                department_id=departments["Operations"].id,
                employee_code="EMP-1000",
                full_name="Super Administrator",
                phone="+919876543210",
                hire_date=date.today() - timedelta(days=365),
                position="Chief Technology Officer",
                salary=Decimal("150000.00"),
                gender="Male",
                employment_status="ACTIVE"
            )
            db.add(super_emp)
            db.commit()
            db.refresh(super_emp)
            bal = LeaveBalance(
                employee_id=super_emp.id,
                annual_total=25,
                annual_used=0,
                sick_total=15,
                sick_used=0,
                casual_total=15,
                casual_used=0,
                unpaid_used=0
            )
            db.add(bal)
            db.commit()
            print("Provisioned Employee profile for Super Admin (EMP-1000)")

        # 3c. Provision Employee for Admin if missing
        if admin_user and not admin_user.employee:
            admin_emp = Employee(
                user_id=admin_user.id,
                department_id=departments["Human Resources"].id,
                employee_code="EMP-1002",
                full_name="System Administrator",
                phone="+919876543211",
                hire_date=date.today() - timedelta(days=200),
                position="HR & Operations Director",
                salary=Decimal("95000.00"),
                gender="Male",
                employment_status="ACTIVE"
            )
            db.add(admin_emp)
            db.commit()
            db.refresh(admin_emp)
            bal = LeaveBalance(
                employee_id=admin_emp.id,
                annual_total=20,
                annual_used=0,
                sick_total=12,
                sick_used=0,
                casual_total=12,
                casual_used=0,
                unpaid_used=0
            )
            db.add(bal)
            db.commit()
            print("Provisioned Employee profile for Admin (EMP-1002)")

        # 4. Seed Sample Employee
        emp_user = db.query(User).filter(User.email == "employee@ems.com").first()
        if not emp_user:
            emp_user = User(
                username="john_doe",
                email="employee@ems.com",
                hashed_password=hash_password("Employee@123"),
                role="EMPLOYEE",
                is_active=True
            )
            db.add(emp_user)
            db.commit()
            db.refresh(emp_user)
            print("Created Employee user: employee@ems.com / Employee@123")

            employee = Employee(
                user_id=emp_user.id,
                department_id=departments["Engineering"].id,
                employee_code="EMP-1001",
                full_name="John Doe",
                phone="+1234567890",
                hire_date=date.today() - timedelta(days=180),
                position="Senior Software Engineer",
                salary=Decimal("85000.00"),
                gender="Male",
                date_of_birth=date(1995, 6, 15),
                address="123 Tech Lane, Silicon Valley, CA",
                employment_status="ACTIVE"
            )
            db.add(employee)
            db.commit()
            db.refresh(employee)

            # Leave Balance
            balance = LeaveBalance(
                employee_id=employee.id,
                year=datetime.now().year,
                annual_total=15,
                annual_used=2,
                sick_total=10,
                sick_used=1,
                casual_total=10,
                casual_used=0,
                unpaid_used=0
            )
            db.add(balance)

            # Salary record
            salary = Salary(
                employee_id=employee.id,
                basic_salary=Decimal("85000.00"),
                allowances=Decimal("5000.00"),
                deductions=Decimal("2000.00"),
                net_salary=Decimal("88000.00"),
                payment_date=date.today(),
                status="PAID",
                payment_method="BANK_TRANSFER",
                notes="Monthly regular salary"
            )
            db.add(salary)
            db.commit()
            print("Created employee profile and balances for John Doe (EMP-1001)")

        # 5. Seed Holidays
        current_year = datetime.now().year
        sample_holidays = [
            ("New Year's Day", date(current_year, 1, 1), "Global celebration"),
            ("Labor Day", date(current_year, 5, 1), "International Workers' Day"),
            ("Independence Day", date(current_year, 7, 4), "National Independence"),
            ("Thanksgiving", date(current_year, 11, 26), "National Holiday"),
            ("Christmas Day", date(current_year, 12, 25), "Christmas holiday")
        ]
        for name, h_date, desc in sample_holidays:
            holiday = db.query(Holiday).filter(Holiday.date == h_date).first()
            if not holiday:
                holiday = Holiday(name=name, date=h_date, description=desc, is_optional=False)
                db.add(holiday)
        db.commit()
        print("Holidays seeded.")

        # 6. Run Enterprise Upgrade & Policy Seeding
        from scripts.upgrade_db import run_db_upgrade
        run_db_upgrade()

        print("Database seeded successfully!")

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
