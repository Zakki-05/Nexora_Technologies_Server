import os
import sys
import random
from datetime import date, datetime, timedelta, time
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, select, text

# Set path to backend
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)

from app.database import Base, fallback_url
from app.models.user import User
from app.models.employee import Employee
from app.models.department import Department
from app.models.leave_balance import LeaveBalance
from app.models.salary_structure import SalaryStructure
from app.models.attendance import Attendance
from app.models.attendance_session import AttendanceSession
from app.utils.security import hash_password

COMPANY_DEPARTMENTS = [
    ("Tata Group - Strategic Industries & Mobility", "Automotive, aerospace, defense systems, and industrial infrastructure"),
    ("Tata Consultancy Services (TCS) - Enterprise Digital Solutions", "Enterprise software, digital core modernisation, and IT services"),
    ("Accenture - Technology Consulting & Cloud", "Strategy consulting, cloud migration, and intelligent enterprise platforms"),
    ("Microsoft - Azure & Enterprise AI", "Hyperscale cloud architecture, OpenAI enterprise integration, and developer platforms"),
    ("Amazon - Global AWS Cloud & Logistics", "Distributed systems, AWS cloud services, and global fulfillment supply chains"),
    ("Google - Cloud Platform & Advanced Engineering", "Kubernetes infrastructure, machine learning pipelines, and cloud analytics"),
    ("Infosys - Digital Innovation & Engineering", "Next-gen digital platforms, AI automation, and enterprise application services"),
    ("Hindustan Unilever - Consumer Goods & Marketing", "Brand growth, consumer market analytics, and FMCG supply operations"),
    ("Reliance Industries - Retail, Telecom & Energy", "Digital telecom, Jio platforms, retail logistics, and green energy systems"),
    ("IBM - Hybrid Cloud & Cognitive Systems", "Red Hat OpenShift integration, AI systems, and enterprise cybersecurity"),
    ("Samsung - Semiconductor & Electronics", "Memory foundries, mobile hardware engineering, and display technology"),
    ("Apple - Operating Systems & Hardware Engineering", "Hardware silicon, iOS/macOS platform architecture, and device ecosystems"),
    ("Oracle - Autonomous Database & SaaS Solutions", "Cloud ERP, high-throughput autonomous database systems, and enterprise middleware"),
    ("Adobe - Digital Media & Creative Experience", "Creative cloud algorithms, PDF systems, and digital experience platforms"),
    ("Intel - Microprocessor Architecture & Foundries", "x86 architecture, semiconductor lithography, and packaging innovation"),
    ("Meta - Reality Labs & AI Infrastructure", "Large-scale AI clusters, PyTorch platform engineering, and social graphs"),
    ("HCLTech - Digital Foundation & Engineering Services", "Infrastructure engineering, digital workplace, and engineering R&D"),
    ("Wipro - Cloud Transformation & Cybersecurity", "Zero-trust security architecture, cloud engineering, and IT modernization"),
    ("Cognizant - Digital Business & Healthcare Operations", "Healthcare analytics, life sciences platforms, and digital operations"),
    ("Capgemini - Global Financial Core & Engineering", "Core banking modernization, payment systems, and financial engineering"),
    ("Deloitte - Advisory, Strategy & Enterprise Risk", "Management consulting, forensic advisory, and enterprise risk management"),
    ("EY - Global Assurance & Transaction Advisory", "Corporate transactions, global audit assurance, and tax technology"),
    ("PwC - Digital Trust & Risk Assurance", "Cybersecurity compliance, ESG governance, and forensic technology"),
    ("KPMG - Deal Advisory & Strategy Consulting", "M&A advisory, operational due diligence, and enterprise transformation"),
]

FIRST_NAMES = [
    "Aarav", "Aditi", "Aditya", "Akash", "Alia", "Ananya", "Anil", "Ankit", "Anushka", "Aravind",
    "Arjun", "Arun", "Aryan", "Ashish", "Avani", "Ayush", "Bhavna", "Chetan", "Deepak", "Deepika",
    "Dev", "Divya", "Gaurav", "Gita", "Harish", "Harsh", "Ishaan", "Ishita", "Jay", "Karan",
    "Karthik", "Kavya", "Kiran", "Komal", "Krishna", "Kunal", "Lakshmi", "Madhav", "Manish", "Meera",
    "Mohit", "Mukesh", "Naveen", "Neha", "Nikhil", "Nisha", "Nitin", "Pankaj", "Pooja", "Pranav",
    "Pranay", "Preeti", "Priya", "Rahul", "Rajesh", "Rakesh", "Ramesh", "Rhea", "Rishi", "Rohan",
    "Rohit", "Roshni", "Sachin", "Sameer", "Sanjay", "Sanya", "Sarita", "Saurabh", "Shalini", "Shashank",
    "Shiv", "Shreya", "Siddharth", "Sneha", "Sonali", "Suman", "Sunil", "Suresh", "Swati", "Tanvi",
    "Tarun", "Uday", "Varun", "Ved", "Vidya", "Vijay", "Vikas", "Vikram", "Vinay", "Vishal",
    "Yash", "Zoya", "Ayesha", "Bilal", "Farhan", "Hamza", "Imran", "Mariam", "Noor", "Rehan",
    "Salim", "Tariq", "Zainab", "Alexander", "Benjamin", "Christopher", "David", "Emily", "Grace", "Hannah"
]

LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Patel", "Singh", "Kumar", "Iyer", "Nair", "Reddy", "Rao",
    "Deshmukh", "Kulkarni", "Joshi", "Bhat", "Mehta", "Shah", "Chopra", "Malhotra", "Kapoor", "Khanna",
    "Bansal", "Agarwal", "Mittal", "Saxena", "Srivastava", "Pandey", "Mishra", "Trivedi", "Shukla", "Chatterjee",
    "Banerjee", "Mukherjee", "Dutta", "Sen", "Bose", "Ghosh", "Menon", "Pillai", "Nambiar", "Shetty",
    "Hegde", "Kamath", "Pai", "Prabhu", "Nadkarni", "Saldanha", "Fernandes", "D'Souza", "Pereira", "Rodrigues",
    "Khan", "Ahmed", "Syed", "Hussain", "Siddiqui", "Qureshi", "Farooqui", "Mirza", "Baig", "Ansari",
    "Tata", "Birla", "Ambani", "Nadar", "Murthy", "Premji", "Godrej", "Piramal", "Munjal", "Poonawalla"
]

POSITIONS_BY_DOMAIN = [
    "Principal Cloud Architect",
    "Staff Software Engineer",
    "Lead AI/ML Research Scientist",
    "Senior Data Platform Engineer",
    "Principal Systems Architect",
    "Senior DevOps & SRE Specialist",
    "Lead Cybersecurity Architect",
    "Enterprise Management Consultant",
    "Senior Strategy Consultant",
    "Director of Enterprise Sales",
    "Principal Product Manager",
    "Senior Financial Analyst",
    "VP Corporate Governance",
    "Global Supply Chain Director",
    "Lead Microprocessor Engineer",
    "Senior Full Stack Developer",
    "Associate Director - Global Assurance",
    "Head of Talent Acquisition",
    "Lead Quality Automation Engineer",
    "Senior Business Intelligence Architect"
]

def seed_enterprise_data(engine):
    print(f"\n=======================================================")
    print(f"[Nexora Seeder] Connecting to database: {engine.url}")
    print(f"=======================================================")

    with Session(engine) as db:
        # 1. Create or fetch departments
        dept_objects = []
        for name, desc in COMPANY_DEPARTMENTS:
            existing = db.query(Department).filter(Department.name == name).first()
            if not existing:
                dept = Department(name=name, description=desc)
                db.add(dept)
                db.flush()
                print(f" + Created Department: {name}")
                dept_objects.append(dept)
            else:
                dept_objects.append(existing)

        db.commit()
        print(f"Total active company departments available: {len(dept_objects)}")

        # 2. Get current employee count and max employee_code
        existing_emp_count = db.query(Employee).count()
        print(f"Current employee count before seed: {existing_emp_count}")

        # Find the highest existing employee code number (e.g. EMP-1056 -> 1056)
        all_codes = db.query(Employee.employee_code).all()
        max_num = 1000
        for (c,) in all_codes:
            if c and c.startswith("EMP-"):
                try:
                    num = int(c.split("-")[1])
                    if num > max_num:
                        max_num = num
                except Exception:
                    pass

        print(f"Starting next employee code from EMP-{max_num + 1}")

        # Pre-compute password hash for 'Employee@123' to make batch insertion fast!
        default_pwd_hash = hash_password("Employee@123")
        admin_pwd_hash = hash_password("Admin@123")

        # 3. Generate 500 realistic employees
        target_new = 500
        print(f"Generating {target_new} enterprise employees...")

        existing_phones = set([p[0] for p in db.query(Employee.phone).all()])
        existing_emails = set([e[0] for e in db.query(User.email).all()])
        existing_usernames = set([u[0] for u in db.query(User.username).all()])

        new_employees = []
        today = date.today()

        for i in range(1, target_new + 1):
            emp_num = max_num + i
            emp_code = f"EMP-{emp_num}"

            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            full_name = f"{first} {last}"

            # Unique username & email
            username_candidate = f"{first.lower()}.{last.lower()}_{emp_num}"
            while username_candidate in existing_usernames:
                username_candidate += f"_{random.randint(10, 99)}"
            existing_usernames.add(username_candidate)

            email_candidate = f"{first.lower()}.{last.lower()}{emp_num}@nexora.tech"
            while email_candidate in existing_emails:
                email_candidate = f"{first.lower()}.{last.lower()}{random.randint(1000, 9999)}@nexora.tech"
            existing_emails.add(email_candidate)

            # Unique phone
            while True:
                phone_candidate = f"+9198{random.randint(10000000, 99999999)}"
                if phone_candidate not in existing_phones:
                    existing_phones.add(phone_candidate)
                    break

            # 1 in 25 is an ADMIN (department lead)
            is_admin = (i % 25 == 0)
            role = "ADMIN" if is_admin else "EMPLOYEE"
            hashed_pwd = admin_pwd_hash if is_admin else default_pwd_hash

            # Create User
            user = User(
                username=username_candidate,
                email=email_candidate,
                hashed_password=hashed_pwd,
                role=role,
                is_active=True
            )
            db.add(user)
            db.flush()

            # Randomize compensation and position
            dept = random.choice(dept_objects)
            position = random.choice(POSITIONS_BY_DOMAIN)
            if is_admin:
                position = f"Head of {dept.name.split(' - ')[0]}"

            # Monthly salary between 45,000 and 280,000
            monthly_salary = Decimal(random.randint(45, 280) * 1000)

            # Hire date in the past 1 to 5 years
            days_ago = random.randint(30, 1800)
            hire_date = today - timedelta(days=days_ago)

            gender = random.choice(["Male", "Female"])

            employee = Employee(
                user_id=user.id,
                department_id=dept.id,
                employee_code=emp_code,
                full_name=full_name,
                phone=phone_candidate,
                hire_date=hire_date,
                position=position,
                salary=monthly_salary,
                gender=gender,
                employment_status="ACTIVE",
                profile_picture_status="APPROVED"
            )
            db.add(employee)
            db.flush()
            new_employees.append(employee)

            # Leave Balances
            annual_u = random.randint(0, 6)
            sick_u = random.randint(0, 3)
            casual_u = random.randint(0, 3)
            lb = LeaveBalance(
                employee_id=employee.id,
                year=today.year,
                annual_total=18,
                annual_used=annual_u,
                sick_total=12,
                sick_used=sick_u,
                casual_total=12,
                casual_used=casual_u,
                unpaid_used=0,
                pending_reserved=0,
                carried_forward=random.randint(0, 5)
            )
            db.add(lb)

            # Salary Structure
            basic = (monthly_salary * Decimal("0.50")).quantize(Decimal("0.01"))
            hra = (monthly_salary * Decimal("0.20")).quantize(Decimal("0.01"))
            da = (monthly_salary * Decimal("0.10")).quantize(Decimal("0.01"))
            conv = Decimal("2000.00")
            med = Decimal("1500.00")
            special = (monthly_salary - basic - hra - da - conv - med).quantize(Decimal("0.01"))
            if special < 0:
                special = Decimal("0.00")

            ss = SalaryStructure(
                employee_id=employee.id,
                basic_salary=basic,
                hra=hra,
                da=da,
                conveyance=conv,
                medical_allowance=med,
                special_allowance=special,
                pf_deduction_rate=Decimal("12.00"),
                professional_tax=Decimal("200.00"),
                esi_rate=Decimal("0.75") if monthly_salary <= 21000 else Decimal("0.00"),
                tds_rate=Decimal("8.00") if monthly_salary > 75000 else Decimal("3.00"),
                is_active=True
            )
            db.add(ss)

            if i % 100 == 0:
                db.commit()
                print(f" -> Committed {i}/{target_new} employees...")

        db.commit()
        print(f"Successfully added all {target_new} employees!")

        # 4. Generate Attendance records for today for ~92% of new employees
        print("Generating realistic shift attendance records for today...")
        for emp in new_employees:
            # 92% attendance rate
            if random.random() < 0.92:
                is_late = random.random() < 0.12
                check_in_h = 9 if not is_late else random.choice([9, 10])
                check_in_m = random.randint(1, 28) if not is_late else random.randint(31, 59)
                check_in_t = time(check_in_h, check_in_m, random.randint(0, 59))

                att = Attendance(
                    employee_id=emp.id,
                    date=today,
                    check_in=check_in_t,
                    status="PRESENT",
                    is_late=is_late,
                    work_hours=Decimal(str(random.choice([8.0, 8.5, 9.0]))),
                    office_duration_minutes=random.randint(480, 540),
                    actual_working_minutes=random.randint(430, 480),
                    total_break_minutes=random.randint(40, 60),
                    paid_break_minutes=20,
                    unpaid_break_minutes=30
                )
                db.add(att)

        db.commit()
        total_now = db.query(Employee).count()
        print(f"Done! Total employee count in DB is now: {total_now}")

def run_seed():
    from app.database import engine, fallback_url

    # 1. Seed Active configured database (Postgres or SQLite)
    seed_enterprise_data(engine)

    # 2. Also ensure SQLite ems.db is updated if active database is PostgreSQL
    if "sqlite" not in str(engine.url):
        print("\nAlso syncing to local SQLite fallback database...")
        sqlite_engine = create_engine(fallback_url, connect_args={"check_same_thread": False})
        seed_enterprise_data(sqlite_engine)

if __name__ == "__main__":
    run_seed()
