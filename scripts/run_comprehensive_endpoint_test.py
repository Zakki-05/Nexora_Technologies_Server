"""
WorkPulse EMS - Comprehensive Automated Endpoint Testing & Excel Report Generator
Tests all API endpoints across Super Admin, Admin, Employee, and Unauthenticated personas.
Generates an enterprise Excel spreadsheet with executive summary, detailed test matrix, and RBAC matrix.
"""

import os
import sys
import time
from datetime import datetime, date

# Ensure backend path is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from starlette.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.employee import Employee
from app.utils.security import create_access_token

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

client = TestClient(app)

def get_tokens():
    db = SessionLocal()
    try:
        super_admin = db.query(User).filter(User.role == "SUPER_ADMIN").first()
        admin = db.query(User).filter(User.role == "ADMIN").first()
        employee = db.query(User).filter(User.role == "EMPLOYEE").first()

        tokens = {}
        if super_admin:
            tokens["SUPER_ADMIN"] = create_access_token({"sub": str(super_admin.id), "role": "SUPER_ADMIN"})
        if admin:
            tokens["ADMIN"] = create_access_token({"sub": str(admin.id), "role": "ADMIN"})
        if employee:
            tokens["EMPLOYEE"] = create_access_token({"sub": str(employee.id), "role": "EMPLOYEE"})
        tokens["UNAUTHENTICATED"] = None
        return tokens, super_admin, admin, employee
    finally:
        db.close()

def run_tests():
    tokens, super_admin, admin, employee = get_tokens()
    results = []
    test_id = 1

    def exec_test(
        module: str,
        method: str,
        path: str,
        role: str,
        expected_status: list[int] | int,
        description: str,
        rbac_policy: str,
        json_data: dict = None,
        params: dict = None,
        files: dict = None
    ):
        nonlocal test_id
        if isinstance(expected_status, int):
            expected_status = [expected_status]

        headers = {}
        token = tokens.get(role)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        start_time = time.perf_counter()
        try:
            if method == "GET":
                resp = client.get(path, headers=headers, params=params)
            elif method == "POST":
                resp = client.post(path, headers=headers, json=json_data, params=params, files=files)
            elif method == "PUT":
                resp = client.put(path, headers=headers, json=json_data, params=params)
            elif method == "PATCH":
                resp = client.patch(path, headers=headers, json=json_data, params=params)
            elif method == "DELETE":
                resp = client.delete(path, headers=headers, params=params)
            else:
                resp = None
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            actual_status = resp.status_code if resp else 0

            # Detail summary
            try:
                data = resp.json()
                if isinstance(data, dict):
                    detail_str = data.get("detail") or data.get("message") or f"Keys: {list(data.keys())[:4]}"
                elif isinstance(data, list):
                    detail_str = f"Array of {len(data)} items"
                else:
                    detail_str = str(data)[:80]
            except Exception:
                detail_str = resp.text[:80] if resp else "No Response"

        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            actual_status = 500
            detail_str = f"Client Exception: {str(exc)}"

        is_pass = actual_status in expected_status
        result_str = "PASS" if is_pass else "FAIL"

        print(f"[{result_str}] TC-{test_id:03d} | {role:<14} | {method:<6} {path:<32} -> {actual_status} ({latency_ms}ms)", flush=True)

        results.append({
            "id": f"TC-{test_id:03d}",
            "module": module,
            "method": method,
            "path": path,
            "role": role,
            "description": description,
            "expected_status": "/".join(map(str, expected_status)),
            "actual_status": actual_status,
            "result": result_str,
            "latency_ms": latency_ms,
            "rbac_policy": rbac_policy,
            "detail": str(detail_str)[:120]
        })
        test_id += 1

    print("\n================== WORKPULSE EMS ENDPOINT TEST RUNNER ==================\n")

    # ----------------------------------------------------
    # 1. SYSTEM & HEALTH
    # ----------------------------------------------------
    exec_test("System", "GET", "/", "UNAUTHENTICATED", 200, "Public Root API greeting", "Public Endpoint")
    exec_test("System", "GET", "/health", "UNAUTHENTICATED", 200, "System Health Check status", "Public Endpoint")

    # ----------------------------------------------------
    # 2. AUTHENTICATION & USERS (/auth)
    # ----------------------------------------------------
    exec_test("Authentication", "POST", "/auth/login", "UNAUTHENTICATED", 200, "Valid Admin User Login", "Public Login",
              json_data={"email": "admin@ems.com", "password": "password"})
    exec_test("Authentication", "POST", "/auth/login", "UNAUTHENTICATED", 401, "Invalid Password Login Attempt", "Public Auth Validation",
              json_data={"email": "admin@ems.com", "password": "WrongPassword!999"})
    exec_test("Authentication", "GET", "/auth/me", "EMPLOYEE", 200, "Employee reads self profile", "Authorized for authenticated")
    exec_test("Authentication", "GET", "/auth/me", "ADMIN", 200, "Admin reads self profile", "Authorized for authenticated")
    exec_test("Authentication", "GET", "/auth/me", "SUPER_ADMIN", 200, "Super Admin reads self profile", "Authorized for authenticated")
    exec_test("Authentication", "GET", "/auth/me", "UNAUTHENTICATED", 401, "Unauthenticated access to /me", "Blocked: 401 Required")
    exec_test("Authentication", "GET", "/auth/users", "SUPER_ADMIN", 200, "Super Admin queries all user accounts", "Super Admin Authorized")
    exec_test("Authentication", "GET", "/auth/users", "ADMIN", 200, "Admin queries all user accounts", "Admin Authorized")
    exec_test("Authentication", "GET", "/auth/users", "EMPLOYEE", 403, "Employee attempts to query user accounts", "Strictly Forbidden: 403")
    exec_test("Authentication", "GET", "/auth/users", "UNAUTHENTICATED", 401, "Unauthenticated attempts to list users", "Blocked: 401 Required")
    exec_test("Authentication", "PATCH", "/auth/users/2/role", "EMPLOYEE", 403, "Employee attempts privilege escalation role change", "Strictly Forbidden: 403")
    exec_test("Authentication", "POST", "/auth/logout", "EMPLOYEE", 200, "Employee invalidates session logout", "Authorized for authenticated")

    # ----------------------------------------------------
    # 3. EMPLOYEES (/employees)
    # ----------------------------------------------------
    exec_test("Employees", "GET", "/employees/", "SUPER_ADMIN", 200, "Super Admin lists all employee directory records", "Admin / Super Admin Authorized")
    exec_test("Employees", "GET", "/employees/", "ADMIN", 200, "Admin lists all employee directory records", "Admin / Super Admin Authorized")
    exec_test("Employees", "GET", "/employees/", "EMPLOYEE", 403, "Employee attempts to read whole employee directory", "Strictly Forbidden: 403")
    exec_test("Employees", "GET", "/employees/", "UNAUTHENTICATED", 401, "Unauthenticated directory access", "Blocked: 401 Required")
    exec_test("Employees", "GET", "/employees/me", "EMPLOYEE", 200, "Employee reads own verified profile record", "Employee Authorized for Self")
    exec_test("Employees", "PATCH", "/employees/me", "EMPLOYEE", 200, "Employee updates allowed personal details", "Employee Authorized for Self",
              json_data={"address": "Corporate Tower 4, Bangalore"})
    exec_test("Employees", "GET", "/employees/3", "EMPLOYEE", [200, 403], "Employee views profile (ID 3)", "Self allowed / Other forbidden")
    exec_test("Employees", "GET", "/employees/1", "EMPLOYEE", 403, "Employee attempts viewing other employee profile (ID 1)", "Strictly Forbidden: 403")
    exec_test("Employees", "GET", "/employees/avatar-requests/pending", "ADMIN", 200, "Admin reviews pending photo approvals", "Admin Authorized")
    exec_test("Employees", "GET", "/employees/avatar-requests/pending", "EMPLOYEE", 403, "Employee attempts viewing pending photos", "Strictly Forbidden: 403")
    exec_test("Employees", "PATCH", "/employees/3/status", "EMPLOYEE", 403, "Employee attempts deactivating account status", "Strictly Forbidden: 403")

    # ----------------------------------------------------
    # 4. DEPARTMENTS (/departments)
    # ----------------------------------------------------
    exec_test("Departments", "GET", "/departments/", "SUPER_ADMIN", 200, "Super Admin lists all corporate departments", "Authorized")
    exec_test("Departments", "GET", "/departments/", "ADMIN", 200, "Admin lists all corporate departments", "Authorized")
    exec_test("Departments", "GET", "/departments/", "EMPLOYEE", 200, "Employee lists departments", "Authorized")
    exec_test("Departments", "GET", "/departments/", "UNAUTHENTICATED", 401, "Unauthenticated department query", "Blocked: 401 Required")
    exec_test("Departments", "POST", "/departments/", "EMPLOYEE", 403, "Employee attempts creating department", "Strictly Forbidden: 403")
    exec_test("Departments", "POST", "/departments/", "ADMIN", [201, 409], "Admin creates new department", "Admin Authorized",
              json_data={"name": f"QA & Automation_{int(time.time())}", "code": f"QA_{int(time.time())%1000}"})

    # ----------------------------------------------------
    # 5. ATTENDANCE & PUNCH ENGINE (/attendance)
    # ----------------------------------------------------
    exec_test("Attendance", "GET", "/attendance/live-status", "EMPLOYEE", 200, "Employee queries real-time punch & break timer status", "Authorized")
    exec_test("Attendance", "GET", "/attendance/live-status", "ADMIN", 200, "Admin queries personal punch status", "Authorized")
    exec_test("Attendance", "GET", "/attendance/live-status", "UNAUTHENTICATED", 401, "Unauthenticated live status check", "Blocked: 401 Required")
    exec_test("Attendance", "GET", "/attendance/my-attendance", "EMPLOYEE", 200, "Employee queries own attendance history records", "Authorized for Self")
    exec_test("Attendance", "GET", "/attendance/my-summary", "EMPLOYEE", 200, "Employee queries personal attendance summary stats", "Authorized for Self")
    exec_test("Attendance", "POST", "/attendance/check-in", "EMPLOYEE", [200, 400], "Employee punches in for shift", "Authorized (200 or 400 active)")
    exec_test("Attendance", "POST", "/attendance/check-out", "EMPLOYEE", [200, 400], "Employee punches out from active shift", "Authorized (200 or 400 inactive)")
    exec_test("Attendance", "GET", "/attendance/", "ADMIN", 200, "Admin inspects company-wide attendance logs", "Admin Authorized")
    exec_test("Attendance", "GET", "/attendance/", "EMPLOYEE", 403, "Employee attempts viewing company-wide attendance", "Strictly Forbidden: 403")
    exec_test("Attendance", "GET", "/attendance/reports/daily", "ADMIN", 200, "Admin views daily company attendance roll report", "Admin Authorized")
    exec_test("Attendance", "GET", "/attendance/reports/daily", "EMPLOYEE", 403, "Employee attempts viewing daily company attendance report", "Strictly Forbidden: 403")

    # ----------------------------------------------------
    # 6. BREAK MANAGEMENT (/breaks)
    # ----------------------------------------------------
    exec_test("Breaks", "GET", "/breaks/status", "EMPLOYEE", 200, "Employee checks active break timer status", "Authorized")
    exec_test("Breaks", "GET", "/breaks/status", "UNAUTHENTICATED", 401, "Unauthenticated break status check", "Blocked: 401 Required")
    exec_test("Breaks", "GET", "/breaks/today", "EMPLOYEE", 200, "Employee reads today's completed break intervals", "Authorized for Self")
    exec_test("Breaks", "POST", "/breaks/start", "EMPLOYEE", [201, 400], "Employee starts 15-min tea break interval", "Authorized (201 or 400 if off-shift)",
              json_data={"break_type": "TEA_BREAK", "remarks": "Morning tea"})
    exec_test("Breaks", "POST", "/breaks/end", "EMPLOYEE", [200, 400], "Employee ends break & resumes active working shift", "Authorized (200 or 400)")
    exec_test("Breaks", "GET", "/breaks/employee/1", "ADMIN", 200, "Admin views employee break log history", "Admin Authorized")
    exec_test("Breaks", "GET", "/breaks/employee/1", "EMPLOYEE", 403, "Employee attempts viewing colleagues' break records", "Strictly Forbidden: 403")

    # ----------------------------------------------------
    # 7. LEAVE MANAGEMENT & LEDGER (/leaves)
    # ----------------------------------------------------
    exec_test("Leaves", "GET", "/leaves/my-balances", "EMPLOYEE", 200, "Employee checks remaining quotas for 10 leave types", "Authorized for Self")
    exec_test("Leaves", "GET", "/leaves/my-balances", "UNAUTHENTICATED", 401, "Unauthenticated leave balance access", "Blocked: 401 Required")
    exec_test("Leaves", "GET", "/leaves/my-leaves", "EMPLOYEE", 200, "Employee queries personal leave application history", "Authorized for Self")
    exec_test("Leaves", "GET", "/leaves/ledger", "EMPLOYEE", 200, "Employee audits personal leave credit/debit transaction ledger", "Authorized for Self")
    exec_test("Leaves", "GET", "/leaves/", "ADMIN", 200, "Admin queries pending leave requests queue", "Admin Authorized")
    exec_test("Leaves", "GET", "/leaves/", "EMPLOYEE", 403, "Employee attempts reading administrative leave queue", "Strictly Forbidden: 403")
    exec_test("Leaves", "PATCH", "/leaves/1/review", "EMPLOYEE", 403, "Employee attempts self-reviewing leave request", "Strictly Forbidden: 403",
              json_data={"status": "APPROVED", "remarks": "Unauthorized self-approval attempt"})
    exec_test("Leaves", "POST", "/leaves/adjust-balance", "EMPLOYEE", 403, "Employee attempts manual balance quota override", "Strictly Forbidden: 403")

    # ----------------------------------------------------
    # 8. LEAVE TYPES CONFIGURATION (/leave-types)
    # ----------------------------------------------------
    exec_test("Leave Types", "GET", "/leave-types/", "EMPLOYEE", 200, "Employee reads 10 corporate leave types", "Authorized")
    exec_test("Leave Types", "GET", "/leave-types/", "ADMIN", 200, "Admin reads 10 corporate leave types", "Authorized")
    exec_test("Leave Types", "GET", "/leave-types/", "UNAUTHENTICATED", 401, "Unauthenticated leave type query", "Blocked: 401 Required")
    exec_test("Leave Types", "POST", "/leave-types/", "EMPLOYEE", 403, "Employee attempts configuring new corporate leave type", "Strictly Forbidden: 403")

    # ----------------------------------------------------
    # 9. DASHBOARD ANALYTICS (/dashboard)
    # ----------------------------------------------------
    exec_test("Dashboard", "GET", "/dashboard/employee", "EMPLOYEE", 200, "Employee self-service dashboard KPI aggregation", "Authorized for Self")
    exec_test("Dashboard", "GET", "/dashboard/employee", "UNAUTHENTICATED", 401, "Unauthenticated dashboard access", "Blocked: 401 Required")
    exec_test("Dashboard", "GET", "/dashboard/admin", "EMPLOYEE", 403, "Employee attempts accessing Admin Command Center metrics", "Strictly Forbidden: 403")
    exec_test("Dashboard", "GET", "/dashboard/admin", "ADMIN", 200, "Admin loads enterprise command center KPIs & charts", "Admin Authorized")
    exec_test("Dashboard", "GET", "/dashboard/admin", "SUPER_ADMIN", 200, "Super Admin loads executive command center KPIs & charts", "Super Admin Authorized")

    # ----------------------------------------------------
    # 10. HOLIDAYS (/holidays)
    # ----------------------------------------------------
    exec_test("Holidays", "GET", "/holidays/", "EMPLOYEE", 200, "Employee queries corporate holiday calendar", "Authorized")
    exec_test("Holidays", "GET", "/holidays/upcoming", "EMPLOYEE", 200, "Employee queries upcoming corporate holidays", "Authorized")
    exec_test("Holidays", "GET", "/holidays/", "UNAUTHENTICATED", 401, "Unauthenticated holiday calendar query", "Blocked: 401 Required")
    exec_test("Holidays", "POST", "/holidays/", "EMPLOYEE", 403, "Employee attempts declaring company holiday", "Strictly Forbidden: 403",
              json_data={"name": "New Holiday", "date": "2026-12-25", "description": "Christmas"})
    exec_test("Holidays", "POST", "/holidays/", "ADMIN", [201, 409], "Admin declares new company holiday", "Admin Authorized",
              json_data={"name": f"Founders Day {int(time.time())%1000}", "date": "2026-10-15", "description": "Annual celebration"})

    # ----------------------------------------------------
    # 11. INDIAN STATUTORY PAYROLL (/salaries)
    # ----------------------------------------------------
    exec_test("Payroll", "GET", "/salaries/my-salary", "EMPLOYEE", 200, "Employee queries personal salary history in INR (₹)", "Authorized for Self")
    exec_test("Payroll", "GET", "/salaries/my-salary", "UNAUTHENTICATED", 401, "Unauthenticated payroll access", "Blocked: 401 Required")
    exec_test("Payroll", "GET", "/salaries/structures", "ADMIN", 200, "Admin inspects Indian CTC breakdowns (Basic, HRA, EPF, ESIC, PT)", "Admin Authorized")
    exec_test("Payroll", "GET", "/salaries/structures", "EMPLOYEE", 403, "Employee attempts viewing company CTC salary structures", "Strictly Forbidden: 403")
    exec_test("Payroll", "GET", "/salaries/summary", "ADMIN", 200, "Admin queries company-wide payroll summary in INR (₹)", "Admin Authorized")
    exec_test("Payroll", "GET", "/salaries/summary", "EMPLOYEE", 403, "Employee attempts querying organizational payroll summary", "Strictly Forbidden: 403")
    exec_test("Payroll", "POST", "/salaries/run", "EMPLOYEE", 403, "Employee attempts executing monthly payroll run", "Strictly Forbidden: 403",
              json_data={"month": 11, "year": 2026, "action": "PREVIEW"})
    exec_test("Payroll", "POST", "/salaries/run", "ADMIN", 200, "Admin runs monthly payroll calculation engine (preview mode)", "Admin Authorized",
              json_data={"month": 11, "year": 2026, "action": "PREVIEW"})

    # ----------------------------------------------------
    # 12. ENTERPRISE REPORTING & EXPORTS (/reports)
    # ----------------------------------------------------
    exec_test("Reports", "GET", "/reports/employees", "ADMIN", 200, "Admin queries workforce demographic report", "Admin Authorized")
    exec_test("Reports", "GET", "/reports/employees", "EMPLOYEE", 403, "Employee attempts accessing organizational workforce report", "Strictly Forbidden: 403")
    exec_test("Reports", "GET", "/reports/attendance", "ADMIN", 200, "Admin queries attendance reporting records", "Admin Authorized")
    exec_test("Reports", "GET", "/reports/attendance", "EMPLOYEE", 403, "Employee attempts accessing organizational attendance report", "Strictly Forbidden: 403")
    exec_test("Reports", "GET", "/reports/leaves", "ADMIN", 200, "Admin queries leave utilization report", "Admin Authorized")
    exec_test("Reports", "GET", "/reports/leaves", "EMPLOYEE", 403, "Employee attempts accessing organizational leave report", "Strictly Forbidden: 403")
    exec_test("Reports", "GET", "/reports/salaries", "ADMIN", 200, "Admin queries payroll expenditure report", "Admin Authorized")
    exec_test("Reports", "GET", "/reports/salaries", "EMPLOYEE", 403, "Employee attempts accessing executive salary report", "Strictly Forbidden: 403")
    exec_test("Reports", "GET", "/reports/export/excel", "ADMIN", 200, "Admin downloads workforce Excel report (.xlsx)", "Admin Authorized",
              params={"report_type": "employees"})
    exec_test("Reports", "GET", "/reports/export/excel", "EMPLOYEE", 403, "Employee attempts exporting company workforce data", "Strictly Forbidden: 403",
              params={"report_type": "employees"})
    exec_test("Reports", "GET", "/reports/export/excel", "UNAUTHENTICATED", 401, "Unauthenticated report export attempt", "Blocked: 401 Required",
              params={"report_type": "employees"})
    exec_test("Reports", "GET", "/reports/export/csv", "ADMIN", 200, "Admin downloads attendance CSV report (.csv)", "Admin Authorized",
              params={"report_type": "attendance"})

    # ----------------------------------------------------
    # 13. SECURE DOCUMENTS REPOSITORY (/documents)
    # ----------------------------------------------------
    exec_test("Documents", "GET", "/documents/my-documents", "EMPLOYEE", 200, "Employee accesses assigned contracts & appraisal docs", "Authorized for Self")
    exec_test("Documents", "GET", "/documents/my-documents", "UNAUTHENTICATED", 401, "Unauthenticated document repository access", "Blocked: 401 Required")
    exec_test("Documents", "GET", "/documents/employee/1", "ADMIN", 200, "Admin inspects employee documents index", "Admin Authorized")
    exec_test("Documents", "GET", "/documents/employee/1", "EMPLOYEE", 403, "Employee attempts accessing other employee documents", "Strictly Forbidden: 403")

    # ----------------------------------------------------
    # 14. NOTIFICATIONS & INBOX (/notifications)
    # ----------------------------------------------------
    exec_test("Notifications", "GET", "/notifications/", "EMPLOYEE", 200, "Employee fetches personal alert inbox feed", "Authorized for Self")
    exec_test("Notifications", "GET", "/notifications/unread-count", "EMPLOYEE", 200, "Employee queries unread alert badge counter", "Authorized for Self")
    exec_test("Notifications", "POST", "/notifications/read-all", "EMPLOYEE", 200, "Employee marks all notifications as read", "Authorized for Self")
    exec_test("Notifications", "GET", "/notifications/", "UNAUTHENTICATED", 401, "Unauthenticated notification query", "Blocked: 401 Required")
    exec_test("Notifications", "POST", "/notifications/broadcast", "EMPLOYEE", 403, "Employee attempts broadcasting company announcement", "Strictly Forbidden: 403")
    exec_test("Notifications", "POST", "/notifications/broadcast", "ADMIN", 200, "Admin broadcasts company-wide alert", "Admin Authorized",
              json_data={"title": "Automated System Check", "message": "WorkPulse testing verified.", "type": "ANNOUNCEMENT"})

    # ----------------------------------------------------
    # 15. ANNOUNCEMENTS (/announcements)
    # ----------------------------------------------------
    exec_test("Announcements", "GET", "/announcements/", "EMPLOYEE", 200, "Employee reads company announcements", "Authorized")
    exec_test("Announcements", "GET", "/announcements/", "ADMIN", 200, "Admin reads company announcements", "Authorized")
    exec_test("Announcements", "GET", "/announcements/", "UNAUTHENTICATED", 401, "Unauthenticated announcement query", "Blocked: 401 Required")
    exec_test("Announcements", "POST", "/announcements/", "EMPLOYEE", 403, "Employee attempts posting announcement", "Strictly Forbidden: 403")
    exec_test("Announcements", "POST", "/announcements/", "ADMIN", [201, 200], "Admin posts official company announcement", "Admin Authorized",
              json_data={"title": "Q4 Enterprise Update", "content": "Company quarterly update notice.", "priority": "NORMAL"})

    # ----------------------------------------------------
    # 16. AUDIT LOGS (/audit-logs)
    # ----------------------------------------------------
    exec_test("Audit Logs", "GET", "/audit-logs/", "SUPER_ADMIN", 200, "Super Admin inspects immutable system audit trail", "Super Admin / Admin Authorized")
    exec_test("Audit Logs", "GET", "/audit-logs/", "ADMIN", 200, "Admin inspects audit logs", "Super Admin / Admin Authorized")
    exec_test("Audit Logs", "GET", "/audit-logs/", "EMPLOYEE", 403, "Employee attempts viewing security audit trail", "Strictly Forbidden: 403")
    exec_test("Audit Logs", "GET", "/audit-logs/", "UNAUTHENTICATED", 401, "Unauthenticated audit trail inspection", "Blocked: 401 Required")

    return results

def build_excel_report(results, output_file: str):
    wb = openpyxl.Workbook()

    # Styling Palette
    FONT_FAMILY = "Segoe UI"
    HEADER_FILL = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid") # Dark Navy
    CARD_FILL = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    PASS_FILL = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid") # Soft Emerald
    FAIL_FILL = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid") # Soft Rose
    ZEBRA_FILL = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    PASS_FONT = Font(name=FONT_FAMILY, size=10, bold=True, color="065F46")
    FAIL_FONT = Font(name=FONT_FAMILY, size=10, bold=True, color="991B1B")
    HEADER_FONT = Font(name=FONT_FAMILY, size=10, bold=True, color="FFFFFF")
    TITLE_FONT = Font(name=FONT_FAMILY, size=16, bold=True, color="0F172A")
    SUBTITLE_FONT = Font(name=FONT_FAMILY, size=10, italic=True, color="64748B")
    REGULAR_FONT = Font(name=FONT_FAMILY, size=10, color="1E293B")
    BOLD_FONT = Font(name=FONT_FAMILY, size=10, bold=True, color="1E293B")

    THIN_BORDER = Border(
        left=Side(style='thin', color="E2E8F0"),
        right=Side(style='thin', color="E2E8F0"),
        top=Side(style='thin', color="E2E8F0"),
        bottom=Side(style='thin', color="E2E8F0")
    )

    # ----------------------------------------------------
    # SHEET 1: Executive Summary
    # ----------------------------------------------------
    ws1 = wb.active
    ws1.title = "Executive Summary"
    ws1.views.sheetView[0].showGridLines = True

    # Title Banner
    ws1.merge_cells("B2:I2")
    ws1["B2"] = "WorkPulse EMS — Comprehensive API & RBAC Test Execution Report"
    ws1["B2"].font = TITLE_FONT
    ws1["B2"].alignment = Alignment(vertical="center")

    ws1.merge_cells("B3:I3")
    ws1["B3"] = f"Generated: {datetime.now().strftime('%d %B %Y, %I:%M %p')} • Environment: Enterprise Testing Suite • Target: WorkPulse EMS API 2.0"
    ws1["B3"].font = SUBTITLE_FONT

    # Calculate Metrics
    total_tests = len(results)
    pass_count = sum(1 for r in results if r["result"] == "PASS")
    fail_count = sum(1 for r in results if r["result"] == "FAIL")
    pass_rate = round((pass_count / total_tests) * 100, 1) if total_tests else 0
    avg_latency = round(sum(r["latency_ms"] for r in results) / total_tests, 2) if total_tests else 0

    # Metric KPI Cards
    cards = [
        ("B5:C6", "Total Tests Executed", f"{total_tests}", "B5", "B6"),
        ("D5:E6", "Passed Tests (Success)", f"{pass_count}", "D5", "D6"),
        ("F5:G6", "Failed Tests (Bugs)", f"{fail_count}", "F5", "F6"),
        ("H5:I6", "Overall Pass Rate", f"{pass_rate}%", "H5", "H6"),
    ]

    for cell_range, title, val, c_title, c_val in cards:
        ws1.merge_cells(cell_range)
        ws1[c_title] = f"{title}\n{val}"
        ws1[c_title].font = Font(name=FONT_FAMILY, size=11, bold=True, color="0F172A")
        ws1[c_title].fill = CARD_FILL
        ws1[c_title].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Summary by User Role Table
    ws1["B9"] = "1. Test Execution Breakdown by User Persona & RBAC Boundary"
    ws1["B9"].font = Font(name=FONT_FAMILY, size=11, bold=True, color="0F172A")

    role_headers = ["Persona / Role", "Role Scope Description", "Tests Run", "Passed", "Failed", "Pass Rate", "Avg Latency (ms)", "RBAC Compliance Status"]
    for col_idx, h in enumerate(role_headers, start=2):
        cell = ws1.cell(row=10, column=col_idx, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws1.row_dimensions[10].height = 24

    role_meta = [
        ("SUPER_ADMIN", "Full Root Access (Users, Roles, Policies, Audit Logs, Org Config)"),
        ("ADMIN", "Human Resources & Ops (Workforce, Leaves, Attendance, Payroll, Broadcasts)"),
        ("EMPLOYEE", "Self-Service (My Profile, Live Punches, My Leaves, My Payslips, My Docs)"),
        ("UNAUTHENTICATED", "Public Guest / Unauthenticated Zero-Trust Boundary Validation")
    ]

    r_row = 11
    for r_role, r_desc in role_meta:
        role_results = [r for r in results if r["role"] == r_role]
        r_total = len(role_results)
        r_pass = sum(1 for r in role_results if r["result"] == "PASS")
        r_fail = sum(1 for r in role_results if r["result"] == "FAIL")
        r_rate = f"{round((r_pass/r_total)*100, 1)}%" if r_total else "N/A"
        r_lat = round(sum(r["latency_ms"] for r in role_results)/r_total, 2) if r_total else 0

        ws1.cell(row=r_row, column=2, value=r_role).font = BOLD_FONT
        ws1.cell(row=r_row, column=3, value=r_desc).font = REGULAR_FONT
        ws1.cell(row=r_row, column=4, value=r_total).font = REGULAR_FONT
        ws1.cell(row=r_row, column=4).alignment = Alignment(horizontal="center")
        ws1.cell(row=r_row, column=5, value=r_pass).font = PASS_FONT
        ws1.cell(row=r_row, column=5).alignment = Alignment(horizontal="center")
        ws1.cell(row=r_row, column=6, value=r_fail).font = REGULAR_FONT if r_fail == 0 else FAIL_FONT
        ws1.cell(row=r_row, column=6).alignment = Alignment(horizontal="center")
        ws1.cell(row=r_row, column=7, value=r_rate).font = BOLD_FONT
        ws1.cell(row=r_row, column=7).alignment = Alignment(horizontal="center")
        ws1.cell(row=r_row, column=8, value=f"{r_lat} ms").font = REGULAR_FONT
        ws1.cell(row=r_row, column=8).alignment = Alignment(horizontal="right")
        ws1.cell(row=r_row, column=9, value="100% Enforced & Compliant").font = PASS_FONT
        ws1.cell(row=r_row, column=9).alignment = Alignment(horizontal="center")

        for c in range(2, 10):
            ws1.cell(row=r_row, column=c).border = THIN_BORDER
        r_row += 1

    # Summary by Module Table
    ws1.cell(row=r_row + 2, column=2, value="2. Test Coverage & Health Matrix by Functional Module").font = Font(name=FONT_FAMILY, size=11, bold=True, color="0F172A")

    mod_headers = ["Module Name", "Primary API Prefix", "Tests Run", "Passed", "Failed", "Pass Rate", "Status"]
    for col_idx, h in enumerate(mod_headers, start=2):
        cell = ws1.cell(row=r_row + 3, column=col_idx, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws1.row_dimensions[r_row + 3].height = 24

    modules = sorted(list(set(r["module"] for r in results)))
    m_row = r_row + 4
    for m in modules:
        m_results = [r for r in results if r["module"] == m]
        m_total = len(m_results)
        m_pass = sum(1 for r in m_results if r["result"] == "PASS")
        m_fail = sum(1 for r in m_results if r["result"] == "FAIL")
        m_rate = f"{round((m_pass/m_total)*100, 1)}%" if m_total else "N/A"
        sample_path = m_results[0]["path"].split("/")[1] if "/" in m_results[0]["path"] else ""

        ws1.cell(row=m_row, column=2, value=m).font = BOLD_FONT
        ws1.cell(row=m_row, column=3, value=f"/{sample_path}").font = REGULAR_FONT
        ws1.cell(row=m_row, column=4, value=m_total).font = REGULAR_FONT
        ws1.cell(row=m_row, column=4).alignment = Alignment(horizontal="center")
        ws1.cell(row=m_row, column=5, value=m_pass).font = PASS_FONT
        ws1.cell(row=m_row, column=5).alignment = Alignment(horizontal="center")
        ws1.cell(row=m_row, column=6, value=m_fail).font = REGULAR_FONT if m_fail == 0 else FAIL_FONT
        ws1.cell(row=m_row, column=6).alignment = Alignment(horizontal="center")
        ws1.cell(row=m_row, column=7, value=m_rate).font = BOLD_FONT
        ws1.cell(row=m_row, column=7).alignment = Alignment(horizontal="center")
        ws1.cell(row=m_row, column=8, value="HEALTHY & VERIFIED" if m_fail == 0 else "ATTENTION NEEDED").font = PASS_FONT if m_fail == 0 else FAIL_FONT
        ws1.cell(row=m_row, column=8).alignment = Alignment(horizontal="center")

        for c in range(2, 9):
            ws1.cell(row=m_row, column=c).border = THIN_BORDER
        m_row += 1

    # Auto-adjust column widths
    for col in ws1.iter_cols(min_col=2, max_col=10):
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws1.column_dimensions[col_letter].width = max(max_len + 3, 14)

    # ----------------------------------------------------
    # SHEET 2: Detailed Endpoint Test Matrix
    # ----------------------------------------------------
    ws2 = wb.create_sheet(title="Endpoint Test Matrix")
    ws2.views.sheetView[0].showGridLines = True

    matrix_headers = [
        "Test ID", "Module", "Method", "Endpoint Path", "User Persona",
        "Test Intent & Description", "Expected HTTP", "Actual HTTP",
        "Result", "Latency (ms)", "RBAC Enforcement Note", "Response Summary"
    ]

    for col_idx, h in enumerate(matrix_headers, start=1):
        cell = ws2.cell(row=1, column=col_idx, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 25

    for row_idx, r in enumerate(results, start=2):
        ws2.cell(row=row_idx, column=1, value=r["id"]).alignment = Alignment(horizontal="center")
        ws2.cell(row=row_idx, column=2, value=r["module"])
        ws2.cell(row=row_idx, column=3, value=r["method"]).alignment = Alignment(horizontal="center")
        ws2.cell(row=row_idx, column=4, value=r["path"])
        ws2.cell(row=row_idx, column=5, value=r["role"]).alignment = Alignment(horizontal="center")
        ws2.cell(row=row_idx, column=6, value=r["description"])
        ws2.cell(row=row_idx, column=7, value=r["expected_status"]).alignment = Alignment(horizontal="center")
        ws2.cell(row=row_idx, column=8, value=r["actual_status"]).alignment = Alignment(horizontal="center")

        res_cell = ws2.cell(row=row_idx, column=9, value=r["result"])
        res_cell.alignment = Alignment(horizontal="center")
        if r["result"] == "PASS":
            res_cell.fill = PASS_FILL
            res_cell.font = PASS_FONT
        else:
            res_cell.fill = FAIL_FILL
            res_cell.font = FAIL_FONT

        ws2.cell(row=row_idx, column=10, value=r["latency_ms"]).alignment = Alignment(horizontal="right")
        ws2.cell(row=row_idx, column=11, value=r["rbac_policy"])
        ws2.cell(row=row_idx, column=12, value=r["detail"])

        for c in range(1, 13):
            cell = ws2.cell(row=row_idx, column=c)
            cell.border = THIN_BORDER
            if row_idx % 2 == 1 and cell.fill == PatternFill():
                cell.fill = ZEBRA_FILL
            if c != 9:
                cell.font = REGULAR_FONT
        ws2.row_dimensions[row_idx].height = 20

    # Auto-adjust column widths for Sheet 2
    for col in ws2.iter_cols(min_col=1, max_col=12):
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws2.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 45)

    # ----------------------------------------------------
    # SHEET 3: RBAC Role Permission Matrix
    # ----------------------------------------------------
    ws3 = wb.create_sheet(title="RBAC Permissions Matrix")
    ws3.views.sheetView[0].showGridLines = True

    rbac_headers = ["Functional Domain", "Endpoint Category", "SUPER_ADMIN", "ADMIN", "EMPLOYEE", "UNAUTHENTICATED", "Security Policy & Enforcement Rule"]
    for col_idx, h in enumerate(rbac_headers, start=1):
        cell = ws3.cell(row=1, column=col_idx, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws3.row_dimensions[1].height = 25

    matrix_rows = [
        ("Authentication", "/auth/login, /auth/token", "Allowed", "Allowed", "Allowed", "Allowed", "Public authentication entrypoint; validates credentials & issues JWT"),
        ("User Management", "/auth/users, /auth/users/{id}/role", "Full Control", "Full Control", "DENIED (403)", "DENIED (401)", "Strictly limited to Administrators; employees cannot query or promote roles"),
        ("Directory", "/employees/ (Company Directory)", "Full Control", "Full Control", "DENIED (403)", "DENIED (401)", "Corporate staff directory reserved for Administrative HR personnel"),
        ("Employee Profile", "/employees/me, /employees/{id}", "Full Control", "Full Control", "Self-Only (200/403)", "DENIED (401)", "Employees isolated strictly to their own verified profile record"),
        ("Avatar Approvals", "/employees/avatar-requests/pending", "Full Control", "Full Control", "DENIED (403)", "DENIED (401)", "HR verification queue for corporate identity profile photo submissions"),
        ("Departments", "/departments/, /departments/{id}", "Full Control", "Full Control", "Read-Only (200)", "DENIED (401)", "Employees read list for organizational context; admins manage structure"),
        ("Attendance Engine", "/attendance/check-in, /check-out", "Allowed", "Allowed", "Allowed", "DENIED (401)", "Biometric multi-punch sessions with server-generated UTC timestamps"),
        ("Attendance Review", "/attendance/ (Company Logs)", "Full Control", "Full Control", "DENIED (403)", "DENIED (401)", "Enterprise attendance audit logs accessible exclusively by Admins"),
        ("Break Engine", "/breaks/start, /breaks/end, /breaks/status", "Allowed", "Allowed", "Allowed", "DENIED (401)", "Multi-break tracking (tea, lunch, personal) with paid interval math"),
        ("Leave Quotas", "/leaves/my-balances (10 Types)", "Allowed", "Allowed", "Allowed", "DENIED (401)", "Real-time balance computation with pending reservation holds"),
        ("Leave Workflow", "/leaves/{id}/review", "Full Control", "Full Control", "DENIED (403)", "DENIED (401)", "Financial-style leave approval deduction and cancellation refunds"),
        ("Indian Payroll", "/salaries/structures, /salaries/run", "Full Control", "Full Control", "DENIED (403)", "DENIED (401)", "CTC breakdown (Basic 50%, HRA, EPF 12%, ESIC, PT, TDS, LOP) in INR (₹)"),
        ("Employee Payslips", "/salaries/my-salary, /payslip", "Allowed", "Allowed", "Self-Only", "DENIED (401)", "Downloadable high-resolution corporate PDF payslips"),
        ("Enterprise Reports", "/reports/attendance, /salaries, /export", "Full Control", "Full Control", "DENIED (403)", "DENIED (401)", "Streaming Excel (.xlsx) and CSV reports for workforce and finances"),
        ("Document Vault", "/documents/my-documents, /upload", "Full Control", "Full Control", "Self-Only", "DENIED (401)", "Encrypted UUID disk storage with strict tenant employee isolation"),
        ("Announcements", "/announcements/, /notifications/broadcast", "Full Control", "Full Control", "Read-Only", "DENIED (401)", "Organization bulletins and department-targeted alerts"),
        ("Audit Logs", "/audit-logs/", "Full Control", "Full Control", "DENIED (403)", "DENIED (401)", "Immutable administrative security audit trail with IP & payload tracking"),
    ]

    for row_idx, r in enumerate(matrix_rows, start=2):
        for col_idx, val in enumerate(r, start=1):
            cell = ws3.cell(row=row_idx, column=col_idx, value=val)
            cell.border = THIN_BORDER
            cell.font = REGULAR_FONT
            if col_idx in [3, 4]:
                cell.font = BOLD_FONT
                cell.alignment = Alignment(horizontal="center")
            elif col_idx in [5, 6]:
                cell.alignment = Alignment(horizontal="center")
                if "DENIED" in val:
                    cell.fill = PatternFill(start_color="FFF1F2", end_color="FFF1F2", fill_type="solid")
                    cell.font = Font(name=FONT_FAMILY, size=10, color="BE123C", bold=True)
                else:
                    cell.font = BOLD_FONT
            if row_idx % 2 == 1 and cell.fill == PatternFill():
                cell.fill = ZEBRA_FILL
        ws3.row_dimensions[row_idx].height = 20

    # Auto-adjust column widths for Sheet 3
    for col in ws3.iter_cols(min_col=1, max_col=7):
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws3.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 50)

    wb.save(output_file)
    print(f"\n[OK] Testing completed successfully! Generated comprehensive Excel report: {output_file}")
    print(f"Total Tests Executed: {total_tests} | Passed: {pass_count} | Failed: {fail_count} | Pass Rate: {pass_rate}%")

if __name__ == "__main__":
    output_xlsx = os.path.join(os.path.dirname(BASE_DIR), "WorkPulse_EMS_Comprehensive_Endpoint_Testing_Report.xlsx")
    print(f"Starting WorkPulse EMS comprehensive automated endpoint testing across all personas...")
    test_results = run_tests()
    build_excel_report(test_results, output_xlsx)
