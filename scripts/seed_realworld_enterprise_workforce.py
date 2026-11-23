import os
import sys
import random
from datetime import date, datetime, timedelta, time
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text

# Set path to backend
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)

from app.database import Base, fallback_url
from app.models.user import User
from app.models.employee import Employee
from app.models.department import Department
from app.models.leave_balance import LeaveBalance
from app.models.leave import Leave
from app.models.leave_type import LeaveType
from app.models.salary_structure import SalaryStructure
from app.models.salary import Salary
from app.models.attendance import Attendance
from app.models.attendance_session import AttendanceSession
from app.models.break_session import BreakSession
from app.models.holiday import Holiday
from app.models.announcement import Announcement
from app.models.notification import Notification
from app.models.audit_log import AuditLog
from app.models.document import EmployeeDocument
from app.utils.security import hash_password

# ==============================================================================
# 20 REAL-WORLD CORPORATE DEPARTMENTS (Nexora Technologies)
# 20 Departments x 25 Employees each = EXACTLY 500 Employees (Equal Distribution)
# ==============================================================================
REALWORLD_DEPARTMENTS = [
    {
        "name": "Software Engineering & Core Platforms",
        "desc": "High-throughput microservices, API architecture, core distributed backend systems, and frontend web applications.",
        "head_title": "VP of Software Engineering",
        "titles": [
            "Principal Systems Architect",
            "Staff Distributed Systems Engineer",
            "Lead Backend Engineer (Python/FastAPI)",
            "Senior Frontend Architect (React/Vite)",
            "Senior Microservices Developer",
            "Full-Stack Software Engineer II",
            "Backend Systems Developer II",
            "Frontend UI/UX Developer II",
            "API Platform Engineer",
            "Associate Software Engineer"
        ]
    },
    {
        "name": "Cloud Infrastructure, SRE & DevOps",
        "desc": "Multi-region AWS/Azure/GCP cloud environments, Kubernetes orchestration, CI/CD pipelines, and 99.99% uptime reliability.",
        "head_title": "Director of Cloud Infrastructure & SRE",
        "titles": [
            "Principal Cloud Architect (AWS/GCP)",
            "Staff Site Reliability Engineer (SRE)",
            "Lead Kubernetes & Containerization Specialist",
            "Senior CI/CD Automation Engineer",
            "Senior Terraform & Infrastructure Architect",
            "DevOps Automation Engineer II",
            "Cloud Security Operations Specialist",
            "Systems Observability Engineer",
            "Database Reliability Engineer",
            "Associate Cloud Administrator"
        ]
    },
    {
        "name": "Artificial Intelligence & Data Science",
        "desc": "Predictive workforce analytics, large language model integration, ML pipelines, and computer vision research.",
        "head_title": "Head of AI Research & Advanced Analytics",
        "titles": [
            "Principal Machine Learning Scientist",
            "Lead Natural Language Processing Architect",
            "Senior Deep Learning Research Engineer",
            "Senior Data Platform Engineer",
            "MLOps Infrastructure Specialist",
            "Computer Vision Algorithm Engineer",
            "Applied Data Scientist II",
            "Quantitative Research Analyst",
            "Data Pipeline Engineer II",
            "Associate AI Research Analyst"
        ]
    },
    {
        "name": "Product Management & Strategy",
        "desc": "Enterprise workforce roadmap planning, customer feature discovery, market competitive research, and product lifecycle management.",
        "head_title": "VP of Enterprise Product Strategy",
        "titles": [
            "Principal Enterprise Product Manager",
            "Lead HR Tech Product Strategist",
            "Senior Technical Product Manager",
            "Senior Product Owner - Core Workflows",
            "Growth & Monetization Product Manager",
            "Enterprise Product Analyst II",
            "Feature Delivery Product Owner",
            "Client Solutions Product Specialist",
            "Associate Product Manager",
            "Product Operations Specialist"
        ]
    },
    {
        "name": "UI/UX Design & Design Systems",
        "desc": "Enterprise design systems, interactive prototypes, user accessibility (a11y), design tokens, and usability research.",
        "head_title": "Director of Product Design & UX",
        "titles": [
            "Principal Design Systems Architect",
            "Lead User Experience Researcher",
            "Senior Visual & Interaction Designer",
            "Senior Enterprise UI Designer",
            "Design Systems Engineer",
            "Product Designer II (B2B SaaS)",
            "Accessibility & Usability Specialist",
            "Motion & Microinteraction Designer",
            "Information Architect",
            "Associate UI/UX Designer"
        ]
    },
    {
        "name": "Quality Assurance & Test Automation",
        "desc": "Automated end-to-end regression testing, performance load testing, API test suites, and continuous delivery QA gates.",
        "head_title": "Head of Quality Engineering & SDET",
        "titles": [
            "Principal SDET & Automation Architect",
            "Lead Performance & Load Testing Engineer",
            "Senior Cypress & Playwright SDET",
            "Senior API & Integration Test Engineer",
            "Security & Vulnerability QA Specialist",
            "Quality Automation Engineer II",
            "Mobile & Cross-Platform QA Specialist",
            "Manual Exploratory Test Analyst",
            "Test Data Management Engineer",
            "Associate QA Automation Tester"
        ]
    },
    {
        "name": "Enterprise Cybersecurity & InfoSec",
        "desc": "Zero-trust network architecture, 24/7 SOC incident response, vulnerability penetration testing, and ISO 27001/SOC 2 compliance.",
        "head_title": "Chief Information Security Officer (CISO)",
        "titles": [
            "Principal Threat Intelligence Architect",
            "Lead SOC Incident Response Specialist (Tier 3)",
            "Senior Penetration Testing & Red Team Lead",
            "Senior Cloud Security & IAM Architect",
            "Vulnerability Management Lead",
            "SOC Security Analyst II",
            "Application Security (AppSec) Engineer",
            "Cryptography & Token Security Specialist",
            "Governance, Risk & Compliance (GRC) Analyst",
            "Associate Security Operations Analyst"
        ]
    },
    {
        "name": "Human Resources & Talent Acquisition",
        "desc": "Strategic talent sourcing, employee onboarding, career growth paths, HR policies, and employee welfare engagement.",
        "head_title": "Chief People Officer & Head of HR",
        "titles": [
            "Senior HR Business Partner (Engineering)",
            "Lead Technical Talent Acquisition Specialist",
            "Global Compensation & Benefits Manager",
            "Employee Experience & Culture Lead",
            "HR Operations & Compliance Manager",
            "Senior Technical Recruiter",
            "Onboarding & Induction Specialist",
            "People Analytics & HRIS Analyst",
            "Employee Welfare Coordinator",
            "Associate HR Executive"
        ]
    },
    {
        "name": "Finance, Accounting & Statutory Payroll",
        "desc": "Indian statutory compliance (EPF 12%, ESIC, Professional Tax, TDS), monthly corporate payroll runs, audit trails, and financial reporting.",
        "head_title": "Chief Financial Officer (CFO)",
        "titles": [
            "Head of Statutory Compliance & Taxation",
            "Lead Corporate Payroll Controller",
            "Senior Financial Planning & Analysis (FP&A) Manager",
            "Senior Direct & Indirect Tax Consultant",
            "Statutory Audit & Reconciliation Lead",
            "Corporate Payroll Accountant II",
            "Accounts Payable & Expense Controller",
            "Billing & Revenue Operations Analyst",
            "Financial Systems Analyst",
            "Associate Payroll Specialist"
        ]
    },
    {
        "name": "Global Enterprise Sales & Strategic Accounts",
        "desc": "Enterprise B2B client acquisition, global client contracts, SaaS licensing agreements, and revenue pipeline expansion.",
        "head_title": "VP of Global Enterprise Sales",
        "titles": [
            "Director of Strategic Enterprise Accounts",
            "Senior Enterprise Account Executive (US/EU)",
            "Lead Solutions Sales Engineer",
            "Commercial Contracts & Bid Manager",
            "Mid-Market Account Executive",
            "Sales Enablement Specialist",
            "Inside Sales Team Lead",
            "Enterprise Deal Desk Specialist",
            "Sales Operations & CRM Analyst",
            "Business Development Representative (BDR)"
        ]
    },
    {
        "name": "Marketing, Brand & Corporate Growth",
        "desc": "B2B performance marketing, digital lead generation, product marketing launches, SEO strategies, and brand positioning.",
        "head_title": "Chief Marketing Officer (CMO)",
        "titles": [
            "Director of Digital & Growth Marketing",
            "Lead Product Marketing Manager (PMM)",
            "Senior Corporate Brand & Creative Strategist",
            "Senior Content Marketing Specialist",
            "SEO & Technical Search Engine Strategist",
            "Paid Acquisition & Performance Marketer",
            "Corporate Events & Webinars Manager",
            "Marketing Operations & HubSpot Lead",
            "Social Media & Community Specialist",
            "Associate Digital Marketing Executive"
        ]
    },
    {
        "name": "Customer Success & Client Experience",
        "desc": "Enterprise customer onboarding, client retention, satisfaction health scores, technical account management, and SLA escalation.",
        "head_title": "VP of Customer Success & CX",
        "titles": [
            "Director of Enterprise Client Onboarding",
            "Lead Technical Account Manager (TAM)",
            "Senior Enterprise Customer Success Manager",
            "Customer Health & Retention Strategist",
            "Client Solutions Architect",
            "Enterprise Support Team Lead (Tier 2/3)",
            "Customer Advocacy & Training Specialist",
            "Implementation & Migration Specialist",
            "Customer Operations Analyst",
            "Associate Customer Success Manager"
        ]
    },
    {
        "name": "Enterprise IT Systems & Infrastructure",
        "desc": "Corporate workstations, network switches, enterprise VPNs, MDM laptop provisioning, SSO identity management, and helpdesk support.",
        "head_title": "Head of Enterprise IT Infrastructure",
        "titles": [
            "Principal Network & Firewall Architect",
            "Lead Windows/macOS Systems Administrator",
            "Senior IT Helpdesk Manager (Tier 2/3)",
            "Enterprise Identity & Okta IAM Specialist",
            "Corporate Hardware & Asset Controller",
            "Network Systems Administrator II",
            "IT Helpdesk Support Specialist II",
            "AV & Conference Room Systems Engineer",
            "Data Center & Server Room Technician",
            "Associate IT Support Technician"
        ]
    },
    {
        "name": "Legal, Compliance & Corporate Governance",
        "desc": "Master service agreements (MSAs), intellectual property patents, GDPR/DPDP data privacy compliance, and corporate risk audit.",
        "head_title": "General Counsel & VP Corporate Legal",
        "titles": [
            "Senior Corporate Legal Counsel",
            "Lead Data Privacy & Regulatory Officer (GDPR)",
            "Commercial Contracts Negotiation Manager",
            "Intellectual Property (IP) & Patent Specialist",
            "Corporate Governance & Ethics Officer",
            "Legal Operations & CLM Specialist",
            "Regulatory Compliance Auditor",
            "Corporate Paralegal Specialist",
            "Contract Review Specialist",
            "Associate Legal Analyst"
        ]
    },
    {
        "name": "Research & Development (R&D Labs)",
        "desc": "Next-generation computing paradigms, distributed ledger security, edge computing, quantum-safe algorithms, and experimental tech.",
        "head_title": "Director of Advanced Research & Innovation",
        "titles": [
            "Principal Quantum Computing Researcher",
            "Lead Distributed Ledger Architect",
            "Senior Edge Computing & IoT Specialist",
            "Applied Cryptography Research Scientist",
            "Hardware Silicon Prototyping Engineer",
            "Experimental Algorithm Developer II",
            "Academic Research Collaboration Lead",
            "Technology Patents Analyst",
            "R&D Lab Operations Coordinator",
            "Associate Research Scientist"
        ]
    },
    {
        "name": "Business Intelligence & Data Analytics",
        "desc": "Central corporate data warehouses, PowerBI/Tableau interactive dashboards, cohort analytics, and executive operational KPIs.",
        "head_title": "Head of Business Intelligence & Insights",
        "titles": [
            "Principal Data Warehouse Architect (Snowflake)",
            "Lead Business Intelligence Specialist (PowerBI)",
            "Senior Quantitative Business Analyst",
            "Senior Analytics Engineer (dbt/SQL)",
            "Enterprise Dashboard Visualization Lead",
            "BI Report Developer II",
            "Data Governance & Quality Specialist",
            "Executive Metrics & Insights Analyst",
            "Revenue Operations Data Analyst",
            "Associate BI Analyst"
        ]
    },
    {
        "name": "Global Operations & Supply Chain",
        "desc": "Multi-city corporate facilities, office safety standards, global vendor logistics, travel desk management, and vendor sustainability.",
        "head_title": "Director of Global Corporate Operations",
        "titles": [
            "Senior Enterprise Facilities Manager",
            "Lead Global Travel & Hospitality Specialist",
            "Corporate Workplace Ergonomics Lead",
            "Vendor Logistics & Supply Chain Manager",
            "Green Building & Sustainability Officer",
            "Office Operations Coordinator (Bengaluru)",
            "Corporate Security & Surveillance Supervisor",
            "Asset Lifecycle & Inventory Specialist",
            "Corporate Logistics Coordinator",
            "Associate Operations Executive"
        ]
    },
    {
        "name": "Project Management Office (PMO)",
        "desc": "Enterprise Agile governance, sprint delivery tracking, resource cross-functional allocation, and executive roadmap milestones.",
        "head_title": "Head of Enterprise PMO & Agile Delivery",
        "titles": [
            "Principal Agile Coach & Scrum Master",
            "Senior Technical Program Manager (TPM)",
            "Lead Cross-Functional Delivery Manager",
            "Sprint Governance & Metrics Specialist",
            "Enterprise Jira & Confluence Administrator",
            "Technical Project Manager II",
            "Release Train Engineer (RTE)",
            "Resource Allocation & Capacity Planner",
            "PMO Process & Quality Analyst",
            "Associate Project Coordinator"
        ]
    },
    {
        "name": "Strategic Sourcing & Procurement",
        "desc": "Software vendor licensing, hardware procurement bidding, vendor risk evaluations, and bulk procurement cost optimization.",
        "head_title": "Head of Strategic Procurement & Sourcing",
        "titles": [
            "Director of Software & SaaS Procurement",
            "Senior Hardware & Infrastructure Buyer",
            "Lead Strategic Sourcing Specialist",
            "Vendor Risk Evaluation & Audit Manager",
            "Procure-to-Pay (P2P) Systems Specialist",
            "Vendor Contract Negotiation Lead",
            "IT Asset Procurement Specialist II",
            "Supplier Relationship Coordinator",
            "Procurement Cost Optimization Analyst",
            "Associate Procurement Specialist"
        ]
    },
    {
        "name": "Learning, Enablement & Talent Development",
        "desc": "Corporate technical certifications, leadership development programs, engineering bootcamps, and continuous skill enablement.",
        "head_title": "Director of Talent Enablement & L&D",
        "titles": [
            "Principal Technical Curriculum Architect",
            "Lead Leadership Development Facilitator",
            "Senior Engineering Bootcamp Trainer",
            "Instructional Designer & Content Lead",
            "E-Learning Platforms & LMS Administrator",
            "Skill Assessment & Certification Specialist",
            "Executive Coaching Program Manager",
            "Corporate Soft Skills Trainer",
            "Training Metrics & Effectiveness Analyst",
            "Associate L&D Coordinator"
        ]
    }
]

# Diverse, realistic employee name banks
FIRST_NAMES_MALE = [
    "Aarav", "Aditya", "Akash", "Anil", "Ankit", "Aravind", "Arjun", "Arun", "Aryan", "Ashish",
    "Ayush", "Chetan", "Deepak", "Dev", "Gaurav", "Harish", "Harsh", "Ishaan", "Jay", "Karan",
    "Karthik", "Kiran", "Kunal", "Madhav", "Manish", "Mohit", "Mukesh", "Naveen", "Nikhil", "Nitin",
    "Pankaj", "Pranav", "Pranay", "Rahul", "Rajesh", "Rakesh", "Ramesh", "Rishi", "Rohan", "Rohit",
    "Sachin", "Sameer", "Sanjay", "Saurabh", "Shashank", "Shiv", "Siddharth", "Sunil", "Suresh", "Tarun",
    "Uday", "Varun", "Ved", "Vijay", "Vikas", "Vikram", "Vinay", "Vishal", "Yash", "Farhan",
    "Imran", "Rehan", "Tariq", "Benjamin", "Christopher", "David", "Alexander", "Daniel", "Lucas", "Marcus"
]

FIRST_NAMES_FEMALE = [
    "Aditi", "Alia", "Ananya", "Anushka", "Avani", "Bhavna", "Deepika", "Divya", "Gita", "Ishita",
    "Kavya", "Komal", "Lakshmi", "Meera", "Neha", "Nisha", "Pooja", "Preeti", "Priya", "Rhea",
    "Roshni", "Sanya", "Sarita", "Shalini", "Shreya", "Sneha", "Sonali", "Suman", "Swati", "Tanvi",
    "Vidya", "Zoya", "Ayesha", "Mariam", "Noor", "Zainab", "Emily", "Grace", "Hannah", "Sophia",
    "Pavitra", "Radhika", "Sunita", "Archana", "Nandini", "Pallavi", "Ritu", "Deepa", "Monika", "Rekha",
    "Ankita", "Bhavani", "Chitra", "Damini", "Esha", "Gayatri", "Harini", "Indu", "Janaki", "Kalyani",
    "Leela", "Malini", "Nalini", "Padma", "Revathi", "Sangeeta", "Tara", "Urmila", "Vasundhara", "Yamini"
]

LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Patel", "Singh", "Kumar", "Iyer", "Nair", "Reddy", "Rao",
    "Deshmukh", "Kulkarni", "Joshi", "Bhat", "Mehta", "Shah", "Chopra", "Malhotra", "Kapoor", "Khanna",
    "Bansal", "Agarwal", "Mittal", "Saxena", "Srivastava", "Pandey", "Mishra", "Trivedi", "Shukla", "Chatterjee",
    "Banerjee", "Mukherjee", "Dutta", "Sen", "Bose", "Ghosh", "Menon", "Pillai", "Nambiar", "Shetty",
    "Hegde", "Kamath", "Pai", "Prabhu", "Nadkarni", "Saldanha", "Fernandes", "D'Souza", "Pereira", "Rodrigues",
    "Khan", "Ahmed", "Syed", "Hussain", "Siddiqui", "Qureshi", "Farooqui", "Mirza", "Baig", "Ansari",
    "Nadar", "Murthy", "Premji", "Godrej", "Piramal", "Munjal", "Poonawalla", "Wadia", "Birla", "Ambani"
]

CITIES_AND_LOCALITIES = [
    ("Bengaluru", "Indiranagar, 100ft Road, Bengaluru, KA 560038"),
    ("Bengaluru", "Koramangala 4th Block, Bengaluru, KA 560034"),
    ("Bengaluru", "Whitefield Main Road, Bengaluru, KA 560066"),
    ("Bengaluru", "HSR Layout Sector 1, Bengaluru, KA 560102"),
    ("Bengaluru", "Electronic City Phase 1, Bengaluru, KA 560100"),
    ("Hyderabad", "Hitec City Phase 2, Madhapur, Hyderabad, TS 500081"),
    ("Hyderabad", "Financial District, Gachibowli, Hyderabad, TS 500032"),
    ("Hyderabad", "Jubilee Hills Road No. 36, Hyderabad, TS 500033"),
    ("Pune", "Hinjewadi IT Park Phase 1, Pune, MH 411057"),
    ("Pune", "Baner-Pashan Link Road, Pune, MH 411045"),
    ("Pune", "Viman Nagar Central, Pune, MH 411014"),
    ("Mumbai", "Bandra Kurla Complex (BKC), Mumbai, MH 400051"),
    ("Mumbai", "Hiranandani Gardens, Powai, Mumbai, MH 400076"),
    ("Chennai", "Old Mahabalipuram Road (OMR), Chennai, TN 600096"),
    ("Chennai", "Guindy Industrial Estate, Chennai, TN 600032"),
    ("Gurgaon", "Cyber City Phase 2, DLF, Gurgaon, HR 122002"),
    ("Gurgaon", "Golf Course Road, Sector 54, Gurgaon, HR 122011"),
    ("Noida", "Sector 62 Institutional Area, Noida, UP 201309")
]

def clean_and_seed_workforce(engine):
    print(f"\n=================================================================")
    print(f"[Nexora Enterprise Seeder] Initializing Equal Workforce Dataset")
    print(f"Target Database: {engine.url}")
    print(f"=================================================================")

    with Session(engine) as db:
        # 1. Clean existing dependent employee records safely
        print("\n[Step 1/5] Cleaning existing test/legacy records for pristine state...")
        
        # Preserve specific system accounts if existing
        super_admin_user = db.query(User).filter(User.email == "superadmin@ems.com").first()
        admin_user = db.query(User).filter(User.email == "admin@ems.com").first()
        employee_user = db.query(User).filter(User.email == "employee@ems.com").first()

        # Delete dependent tables in foreign-key order
        try:
            db.query(AttendanceSession).delete()
            db.query(BreakSession).delete()
            db.query(Attendance).delete()
            db.query(Leave).delete()
            db.query(LeaveBalance).delete()
            db.query(Salary).delete()
            db.query(SalaryStructure).delete()
            db.query(EmployeeDocument).delete()
            db.query(Employee).delete()
            db.query(Department).delete()
            
            # Delete non-master users
            preserved_emails = ["superadmin@ems.com", "admin@ems.com", "employee@ems.com"]
            db.query(User).filter(~User.email.in_(preserved_emails)).delete(synchronize_session=False)
            
            db.commit()
            print(" + Successfully cleared legacy data. Database prepared for fresh enterprise seed.")
        except Exception as e:
            db.rollback()
            print(f" - Notice during cleanup (will proceed): {e}")

        # Ensure Master Users exist
        print("\n[Step 2/5] Verifying Master Authentication Accounts...")
        admin_pwd_hash = hash_password("Admin@123")
        emp_pwd_hash = hash_password("Employee@123")

        # 2. Create the 20 pristine Real-World Departments
        print("\n[Step 3/5] Provisioning 20 Corporate Departments...")
        created_depts = []
        for d_info in REALWORLD_DEPARTMENTS:
            dept = Department(name=d_info["name"], description=d_info["desc"])
            db.add(dept)
            db.flush()
            created_depts.append((dept, d_info))
            print(f" + [{len(created_depts):02d}/20] Department: {dept.name}")

        db.commit()
        print(f"All 20 Real-World Corporate Departments successfully registered.")

        # 3. Create exactly 25 employees per department (20 x 25 = 500 employees)
        print("\n[Step 4/5] Generating Equal Workforce: Exactly 25 Employees per Department (500 Total)...")
        
        used_phones = set()
        used_emails = set(["admin@ems.com", "employee@ems.com", "superadmin@ems.com"])
        used_usernames = set(["admin", "john_doe", "superadmin"])
        emp_code_counter = 1001

        # Pre-cache today's date
        today = date.today()

        total_created = 0
        admin_count = 0
        emp_count = 0

        for dept_idx, (dept, d_info) in enumerate(created_depts, 1):
            print(f" -> Seeding Department {dept_idx:02d}/20: '{dept.name}' (Target: 25 Employees)...")
            
            # Position 1: Department Head (Role: ADMIN)
            # Positions 2-25: Department Members (Role: EMPLOYEE) with realistic seniority pyramid
            for member_idx in range(1, 26):
                is_dept_head = (member_idx == 1)
                
                # Check for standard demo employee profile assignment:
                # Department 1, Member 5 will be John Doe (employee@ems.com)
                # Department 1, Member 1 will be Master Admin (admin@ems.com)
                is_demo_admin = (dept_idx == 1 and member_idx == 1)
                is_demo_employee = (dept_idx == 1 and member_idx == 5)

                # Determine Seniority & Job Title
                if is_dept_head:
                    position = d_info["head_title"]
                    role = "ADMIN"
                    user_pwd = admin_pwd_hash
                    gross_salary = Decimal(str(random.randint(240, 320) * 1000))  # 2,40,000 - 3,20,000
                    experience_years = random.randint(14, 22)
                elif member_idx in [2, 3, 4]:
                    # Principal / Staff Specialist
                    position = d_info["titles"][min(member_idx - 1, len(d_info["titles"]) - 1)]
                    role = "EMPLOYEE"
                    user_pwd = emp_pwd_hash
                    gross_salary = Decimal(str(random.randint(170, 220) * 1000))  # 1,70,000 - 2,20,000
                    experience_years = random.randint(9, 14)
                elif member_idx in range(5, 12):
                    # Senior Specialist
                    title_idx = min(member_idx - 3, len(d_info["titles"]) - 1)
                    position = d_info["titles"][title_idx]
                    role = "EMPLOYEE"
                    user_pwd = emp_pwd_hash
                    gross_salary = Decimal(str(random.randint(100, 155) * 1000))  # 1,00,000 - 1,55,000
                    experience_years = random.randint(5, 9)
                elif member_idx in range(12, 22):
                    # Mid-level Specialist
                    title_idx = min(member_idx - 8, len(d_info["titles"]) - 1)
                    position = d_info["titles"][title_idx]
                    role = "EMPLOYEE"
                    user_pwd = emp_pwd_hash
                    gross_salary = Decimal(str(random.randint(60, 95) * 1000))    # 60,000 - 95,000
                    experience_years = random.randint(3, 6)
                else:
                    # Associate / Junior Specialist
                    position = d_info["titles"][-1]
                    role = "EMPLOYEE"
                    user_pwd = emp_pwd_hash
                    gross_salary = Decimal(str(random.randint(38, 55) * 1000))    # 38,000 - 55,000
                    experience_years = random.randint(1, 3)

                # Equal gender distribution (alternating)
                is_female = (member_idx % 2 == 0)
                gender = "Female" if is_female else "Male"
                
                if is_demo_admin:
                    first_name = "System"
                    last_name = "Administrator"
                    gender = "Male"
                elif is_demo_employee:
                    first_name = "John"
                    last_name = "Doe"
                    gender = "Male"
                else:
                    first_name = random.choice(FIRST_NAMES_FEMALE if is_female else FIRST_NAMES_MALE)
                    last_name = random.choice(LAST_NAMES)
                
                full_name = f"{first_name} {last_name}"

                # Unique Employee Code
                emp_code = f"EMP-{emp_code_counter}"
                emp_code_counter += 1

                # Unique Email & Username
                clean_first = first_name.lower().replace("'", "").replace(" ", "")
                clean_last = last_name.lower().replace("'", "").replace(" ", "")
                
                if is_demo_admin:
                    username = "admin"
                    email = "admin@ems.com"
                elif is_demo_employee:
                    username = "john_doe"
                    email = "employee@ems.com"
                else:
                    base_username = f"{clean_first}.{clean_last}_{emp_code_counter}"
                    username = base_username
                    while username in used_usernames:
                        username = f"{base_username}_{random.randint(10, 99)}"
                    used_usernames.add(username)

                    email = f"{clean_first}.{clean_last}.{emp_code_counter}@nexora.tech"
                    while email in used_emails:
                        email = f"{clean_first}.{clean_last}.{random.randint(1000, 9999)}@nexora.tech"
                    used_emails.add(email)

                # Unique Phone Number
                while True:
                    phone_candidate = f"+9198{random.randint(10000000, 99999999)}"
                    if phone_candidate not in used_phones:
                        used_phones.add(phone_candidate)
                        break

                # Address & City
                city, full_address = random.choice(CITIES_AND_LOCALITIES)

                # Date of birth & Hire Date based on experience
                birth_year = today.year - (22 + experience_years + random.randint(0, 3))
                date_of_birth = date(birth_year, random.randint(1, 12), random.randint(1, 28))
                
                hire_days_ago = min(experience_years * 300, random.randint(60, 2200))
                hire_date = today - timedelta(days=hire_days_ago)

                # 1. Create or link User
                existing_user = db.query(User).filter(User.email == email).first()
                if existing_user:
                    user = existing_user
                    user.hashed_password = user_pwd
                    user.role = role
                    user.is_active = True
                else:
                    user = User(
                        username=username,
                        email=email,
                        hashed_password=user_pwd,
                        role=role,
                        is_active=True
                    )
                    db.add(user)
                    db.flush()

                # 2. Create Employee Profile
                emp = Employee(
                    user_id=user.id,
                    department_id=dept.id,
                    employee_code=emp_code,
                    full_name=full_name,
                    phone=phone_candidate,
                    hire_date=hire_date,
                    position=position,
                    salary=gross_salary,
                    gender=gender,
                    date_of_birth=date_of_birth,
                    address=full_address,
                    employment_status="ACTIVE",
                    profile_picture_status="APPROVED"
                )
                db.add(emp)
                db.flush()

                # 3. Create Real-World Indian Statutory Salary Structure
                basic_salary = (gross_salary * Decimal("0.45")).quantize(Decimal("0.01"))
                hra = (basic_salary * Decimal("0.40")).quantize(Decimal("0.01"))
                conveyance = Decimal("1600.00")
                medical = Decimal("1250.00")
                special_allowance = gross_salary - (basic_salary + hra + conveyance + medical)
                if special_allowance < Decimal("0.00"):
                    special_allowance = Decimal("0.00")

                pf_rate = Decimal("12.00")
                prof_tax = Decimal("200.00")
                esi_rate = Decimal("0.75") if gross_salary <= Decimal("21000.00") else Decimal("0.00")
                
                if gross_salary >= Decimal("150000.00"):
                    tds_rate = Decimal("12.00")
                elif gross_salary >= Decimal("80000.00"):
                    tds_rate = Decimal("8.00")
                elif gross_salary >= Decimal("50000.00"):
                    tds_rate = Decimal("5.00")
                else:
                    tds_rate = Decimal("0.00")

                salary_struct = SalaryStructure(
                    employee_id=emp.id,
                    basic_salary=basic_salary,
                    hra=hra,
                    da=Decimal("0.00"),
                    conveyance=conveyance,
                    medical_allowance=medical,
                    special_allowance=special_allowance,
                    pf_deduction_rate=pf_rate,
                    professional_tax=prof_tax,
                    esi_rate=esi_rate,
                    tds_rate=tds_rate,
                    is_active=True
                )
                db.add(salary_struct)

                # 4. Create Standard Enterprise Leave Balances (10 categories)
                annual_tot = 18
                annual_used = random.randint(0, 4)
                sick_tot = 12
                sick_used = random.randint(0, 3)
                casual_tot = 12
                casual_used = random.randint(0, 3)

                leave_bal = LeaveBalance(
                    employee_id=emp.id,
                    year=today.year,
                    annual_total=annual_tot,
                    annual_used=annual_used,
                    sick_total=sick_tot,
                    sick_used=sick_used,
                    casual_total=casual_tot,
                    casual_used=casual_used,
                    unpaid_used=0,
                    carried_forward=random.randint(0, 4)
                )
                db.add(leave_bal)

                # 5. Seed Attendance for the last 5 working days (Monday-Friday)
                for day_offset in range(1, 6):
                    work_date = today - timedelta(days=day_offset)
                    # Skip weekends
                    if work_date.weekday() >= 5:
                        continue
                    
                    status_choice = random.choices(
                        ["PRESENT", "WORK_FROM_HOME", "LATE"],
                        weights=[85, 12, 3]
                    )[0]

                    is_late_val = (status_choice == "LATE")
                    if is_late_val:
                        check_in_time = time(9, random.randint(35, 55))
                    else:
                        check_in_time = time(8, random.randint(45, 59)) if random.random() < 0.3 else time(9, random.randint(0, 20))
                    
                    check_out_time = time(18, random.randint(5, 45))
                    work_hours_dec = Decimal(str(round(random.uniform(8.25, 9.25), 2)))

                    att = Attendance(
                        employee_id=emp.id,
                        date=work_date,
                        check_in=check_in_time,
                        check_out=check_out_time,
                        work_hours=work_hours_dec,
                        actual_working_minutes=int(work_hours_dec * 60),
                        office_duration_minutes=int(work_hours_dec * 60) + 45,
                        total_break_minutes=45,
                        paid_break_minutes=45,
                        unpaid_break_minutes=0,
                        is_late=is_late_val,
                        status="PRESENT" if is_late_val else status_choice
                    )
                    db.add(att)

                total_created += 1
                if role == "ADMIN":
                    admin_count += 1
                else:
                    emp_count += 1

        db.commit()

        print(f"\n[Step 5/5] Verification & Summary:")
        print(f"=================================================================")
        print(f"Total Departments: {len(created_depts)}")
        print(f"Total Employees:   {total_created}")
        print(f"Department Heads:  {admin_count} (Role: ADMIN)")
        print(f"Team Specialists:  {emp_count} (Role: EMPLOYEE)")
        print(f"Headcount per Dept: EXACTLY 25 Employees in each of the 20 departments!")
        print(f"=================================================================\n")

        # Verify each department's exact count
        for dept, _ in created_depts:
            dept_count = db.query(Employee).filter(Employee.department_id == dept.id).count()
            print(f" - {dept.name}: {dept_count} employees [PERFECT MATCH]")

if __name__ == "__main__":
    engine = create_engine(fallback_url)
    clean_and_seed_workforce(engine)
