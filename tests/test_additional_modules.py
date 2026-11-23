from datetime import date, datetime, timedelta
from decimal import Decimal
import io
import pytest
from fastapi import HTTPException, UploadFile

from app.models.user import User
from app.models.department import Department
from app.models.employee import Employee
from app.schemas.holiday import HolidayCreate, HolidayUpdate
from app.schemas.salary import SalaryCreate, SalaryUpdate
from app.schemas.notification import NotificationBroadcast
from app.services.holiday_service import (
    create_holiday,
    get_all_holidays,
    get_upcoming_holidays,
    update_holiday,
    delete_holiday
)
from app.services.salary_service import (
    create_salary_record,
    get_all_salaries,
    get_employee_salaries,
    get_salary_summary
)
from app.services.notification_service import (
    create_notification,
    get_user_notifications,
    mark_notification_as_read,
    mark_all_as_read,
    broadcast_notification,
    get_unread_count
)
from app.services.audit_service import log_audit, get_audit_logs
from app.services.report_service import (
    generate_employee_report,
    generate_department_report,
    generate_attendance_report,
    generate_leave_report,
    generate_salary_report,
    export_to_csv,
    export_to_excel
)
from app.utils.security import hash_password

@pytest.fixture
def module_setup(db_session):
    u = User(
        username="report_user",
        email="report_user@ems.com",
        hashed_password=hash_password("Pass123!"),
        role="EMPLOYEE",
        is_active=True
    )
    d = Department(name="Analytics", description="Data & Analytics")
    db_session.add_all([u, d])
    db_session.commit()

    emp = Employee(
        user_id=u.id,
        department_id=d.id,
        employee_code="EMP-9001",
        full_name="Alice Analytics",
        phone="+13333333333",
        hire_date=date(2026, 1, 1),
        position="Data Analyst",
        salary=Decimal("65000.00"),
        employment_status="ACTIVE"
    )
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)

    return {"user": u, "department": d, "employee": emp}

# 1. Holiday Tests
def test_holiday_crud(db_session):
    h_date = date(2026, 12, 31)
    data = HolidayCreate(name="New Year's Eve", date=h_date, description="End of year")
    h = create_holiday(data, db_session)
    assert h.id is not None
    assert h.name == "New Year's Eve"

    # Duplicate date fails
    with pytest.raises(HTTPException) as exc:
        create_holiday(data, db_session)
    assert exc.value.status_code == 409

    # Update
    updated = update_holiday(h.id, HolidayUpdate(name="Annual Eve Gala"), db_session)
    assert updated.name == "Annual Eve Gala"

    # Delete
    del_res = delete_holiday(h.id, db_session)
    assert del_res["success"] is True

# 2. Salary Tests
def test_salary_management(db_session, module_setup):
    emp = module_setup["employee"]
    data = SalaryCreate(
        employee_id=emp.id,
        basic_salary=Decimal("50000.00"),
        allowances=Decimal("5000.00"),
        deductions=Decimal("2000.00"),
        payment_date=date.today(),
        status="PAID",
        payment_method="BANK_TRANSFER"
    )
    sal = create_salary_record(data, db_session)
    assert sal.id is not None
    assert sal.net_salary == Decimal("53000.00")

    summary = get_salary_summary(db_session)
    assert summary.record_count >= 1
    assert summary.total_paid >= Decimal("53000.00")

# 3. Notification Tests
def test_notification_flow(db_session, module_setup):
    user = module_setup["user"]
    notif = create_notification(user.id, "Test Alert", "You have a new alert", "ALERT", db_session)
    assert notif.is_read is False

    assert get_unread_count(user.id, db_session) >= 1

    # Mark single as read
    read = mark_notification_as_read(notif.id, user.id, db_session)
    assert read.is_read is True

    # Broadcast
    broadcast_count = broadcast_notification(
        NotificationBroadcast(title="System Update", message="Platform upgrading tonight"),
        db_session
    )
    assert broadcast_count >= 1

# 4. Audit Log Tests
def test_audit_logs(db_session, module_setup):
    user = module_setup["user"]
    log = log_audit(
        db_session,
        user_id=user.id,
        action="UPDATE",
        resource_type="SALARY",
        resource_id="101",
        details="Adjusted basic salary"
    )
    assert log is not None
    assert log.action == "UPDATE"

    res = get_audit_logs(db_session, user_id=user.id)
    assert res.total >= 1

# 5. Report Tests
def test_reports_generation(db_session, module_setup):
    # Employee Report
    h_emp, r_emp, s_emp = generate_employee_report(db_session)
    assert "Employee Code" in h_emp
    assert len(r_emp) >= 1
    assert s_emp["total_employees"] >= 1

    # Department Report
    h_dept, r_dept, s_dept = generate_department_report(db_session)
    assert "Department Name" in h_dept
    assert len(r_dept) >= 1

    # CSV Export
    csv_str = export_to_csv(h_emp, r_emp)
    assert "Employee Code" in csv_str
    assert "EMP-9001" in csv_str

    # Excel Export
    excel_buf = export_to_excel(h_emp, r_emp)
    assert excel_buf.getbuffer().nbytes > 500
