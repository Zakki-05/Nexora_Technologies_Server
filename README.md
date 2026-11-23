# Nexora Technologies Server

> **Enterprise-Grade Workforce & HR Management System (EMS) — Core Backend API**

Built with **Python**, **FastAPI**, **SQLAlchemy**, **Pydantic v2**, and **PostgreSQL / SQLite**.

---

## Architecture & Features

- **JWT Authentication & RBAC**: Bank-grade 256-bit token authentication supporting `SUPER_ADMIN`, `ADMIN`, and `EMPLOYEE` roles with granular permission dependencies.
- **Precision Attendance Engine**: Microsecond-precision multi-session shift tracking with idempotent check-in, check-out, and break management.
- **10-Quota Statutory Leave Ledgers**: Full leave balance ledger system with automatic accrual, policy management, and workflow approvals.
- **Statutory Indian Payroll Engine**: Automated calculations for Gross Salary, Basic, HRA, DA, EPF (12%), and ESIC (0.75%/3.25%) with PDF pay slip generation.
- **Auditing & Security**: Tamper-evident audit logs, rate-limited endpoints, and robust error handling.
- **Dual Database Support**: Production PostgreSQL with seamless local SQLite fallback.

---

## Tech Stack

- **Framework**: FastAPI (Asynchronous Python REST API)
- **ORM & DB**: SQLAlchemy 2.0, Alembic (Migrations), PostgreSQL / SQLite
- **Validation**: Pydantic v2, Pydantic-Settings
- **Security**: Passlib / Bcrypt, Python-Jose (JWT), Cryptography
- **Server**: Uvicorn ASGI Server

---

## Getting Started

### 1. Prerequisites
- Python 3.10+ (Python 3.11/3.12 recommended)
- PostgreSQL (or local SQLite)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/Zakki-05/Nexora_Technologies_Server.git
cd Nexora_Technologies_Server

# Create virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```env
DATABASE_URL=postgresql+psycopg2://postgres:password@localhost:5432/ems
SECRET_KEY=your-super-secret-jwt-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
ENVIRONMENT=development
CORS_ORIGINS=["http://localhost:5173","https://dev-zakki.vercel.app"]
```

### 4. Run the API Server
```bash
uvicorn app.main:app --reload --port 8000
```

- **Live API Endpoint**: `https://nexora-technologies-server.onrender.com`
- **Interactive Swagger Docs**: `https://nexora-technologies-server.onrender.com/docs`
- **ReDoc Documentation**: `https://nexora-technologies-server.onrender.com/redoc`

---

## Deployment

- **Vercel**: Pre-configured with `vercel.json` rewrites to `/api/index.py`.
- **Render / Railway / Docker**: Use `Procfile` or `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

---

## Author & Lead Architect

**Mohammed Zakki Adnaan P**  
*Python Full Stack & React.js Developer*  
- **Portfolio**: [dev-zakki.vercel.app](https://dev-zakki.vercel.app/)  
- **GitHub**: [@Zakki-05](https://github.com/Zakki-05)  
- **LinkedIn**: [mohammed-zakki-adnan-p](https://www.linkedin.com/in/mohammed-zakki-adnan-p/)  
- **Email**: zakkiadnan05@gmail.com  

---

© 2026 Nexora Technologies Inc. All rights reserved.
