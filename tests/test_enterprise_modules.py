import io
import os
from datetime import date, datetime, timedelta
from decimal import Decimal
import pytest
from fastapi import HTTPException, UploadFile

from app.models.user import User
from app.models.department import Department
from app.models.employee import Employee
from app.models.announcement import Announcement
from app.models.notification import Notification
from app.models.document import EmployeeDocument
from app.schemas.announcement import AnnouncementCreate, AnnouncementUpdate
from app.schemas.notification import NotificationBroadcast
from app.services.announcement_service import (
    create_announcement,
    get_announcements_for_user,
    get_announcement_by_id,
    update_announcement,
    delete_announcement
)
from app.services.notification_service import (
    create_notification,
    get_user_notifications,
    mark_notification_as_read,
    mark_all_as_read,
    get_unread_count,
    delete_notification,
    broadcast_notification
)
from app.services.audit_service import log_audit, get_audit_logs
from app.services.document_service import (
    upload_document,
    get_employee_documents,
    get_document_by_id,
    delete_document,
    MAX_FILE_SIZE
)
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
def enterprise_setup(db_session):
    admin = User(
        username="admin_corp",
        email="admin_corp@ems.com",
        hashed_password=hash_password("AdminCorp123!"),
        role="ADMIN",
        is_active=True
    )
    user_eng = User(
        username="eng_user",
        email="eng_user@ems.com",
        hashed_password=hash_password("EngUser123!"),
        role="EMPLOYEE",
        is_active=True
    )
    user_sales = User(
        username="sales_user",
        email="sales_user@ems.com",
        hashed_password=hash_password("SalesUser123!"),
        role="EMPLOYEE",
        is_active=True
    )
    dept_eng = Department(name="R&D Engineering", description="Engineering team")
    dept_sales = Department(name="Global Sales", description="Sales team")
    db_session.add_all([admin, user_eng, user_sales, dept_eng, dept_sales])
    db_session.commit()

    emp_eng = Employee(
        user_id=user_eng.id,
        department_id=dept_eng.id,
        employee_code="EMP-ENG-1",
        full_name="Edward Engineer",
        phone="+91999990001",
        hire_date=date(2025, 1, 1),
        position="Senior Developer",
        salary=Decimal("75000.00"),
        employment_status="ACTIVE"
    )
    emp_sales = Employee(
        user_id=user_sales.id,
        department_id=dept_sales.id,
        employee_code="EMP-SAL-1",
        full_name="Sally Sales",
        phone="+91999990002",
        hire_date=date(2025, 2, 1),
        position="Account Executive",
        salary=Decimal("60000.00"),
        employment_status="ACTIVE"
    )
    db_session.add_all([emp_eng, emp_sales])
    db_session.commit()
    db_session.refresh(emp_eng)
    db_session.refresh(emp_sales)

    return {
        "admin": admin,
        "user_eng": user_eng,
        "user_sales": user_sales,
        "emp_eng": emp_eng,
        "emp_sales": emp_sales,
        "dept_eng": dept_eng,
        "dept_sales": dept_sales
    }

# ==================== TEST SUITE ====================

def test_announcements_priority_targeting_and_broadcast(db_session, enterprise_setup):
    admin = enterprise_setup["admin"]
    user_eng = enterprise_setup["user_eng"]
    user_sales = enterprise_setup["user_sales"]
    dept_eng = enterprise_setup["dept_eng"]

    # 1. Create Urgent Organization-wide announcement (with notification broadcast)
    urgent_all = create_announcement(AnnouncementCreate(
        title="Fire Drill Tomorrow",
        message="Mandatory fire drill at 11 AM",
        priority="URGENT",
        target_type="ALL",
        broadcast_notification=True
    ), admin.id, db_session, ip_address="192.168.1.100")
    assert urgent_all.id is not None
    assert urgent_all.priority == "URGENT"

    # Verify both users got notification
    notif_eng = get_user_notifications(user_eng.id, db_session)
    notif_sales = get_user_notifications(user_sales.id, db_session)
    assert any("Fire Drill" in n.title for n in notif_eng.items)
    assert any("Fire Drill" in n.title for n in notif_sales.items)

    # 2. Create High Announcement targeted ONLY to Engineering
    eng_only = create_announcement(AnnouncementCreate(
        title="Code Freeze Next Week",
        message="Feature branch freeze for release 2.0",
        priority="HIGH",
        target_type="DEPARTMENT",
        target_department_id=dept_eng.id,
        broadcast_notification=True
    ), admin.id, db_session)
    assert eng_only.id is not None

    # 3. Create Expired announcement
    expired = create_announcement(AnnouncementCreate(
        title="Past Event Notice",
        message="This event has passed",
        priority="NORMAL",
        target_type="ALL",
        expires_at=datetime.now() - timedelta(days=2),
        broadcast_notification=False
    ), admin.id, db_session)

    # 4. Check Engineering employee feed
    eng_feed = get_announcements_for_user(user_eng, db_session)
    eng_titles = [a.title for a in eng_feed.items]
    assert "Fire Drill Tomorrow" in eng_titles
    assert "Code Freeze Next Week" in eng_titles
    assert "Past Event Notice" not in eng_titles  # Expired must be excluded
    # Priority check: URGENT first, then HIGH
    assert eng_feed.items[0].priority == "URGENT"

    # 5. Check Sales employee feed: should NOT see Engineering's announcement
    sales_feed = get_announcements_for_user(user_sales, db_session)
    sales_titles = [a.title for a in sales_feed.items]
    assert "Fire Drill Tomorrow" in sales_titles
    assert "Code Freeze Next Week" not in sales_titles

    # 6. Update and Delete
    updated = update_announcement(urgent_all.id, AnnouncementUpdate(
        title="Rescheduled Fire Drill"
    ), admin.id, db_session)
    assert updated.title == "Rescheduled Fire Drill"

    del_res = delete_announcement(urgent_all.id, admin.id, db_session)
    assert del_res["success"] is True

def test_notification_hub_mark_all_read_and_delete(db_session, enterprise_setup):
    user = enterprise_setup["user_eng"]

    # Clear prior notifs
    for n in db_session.query(Notification).filter(Notification.user_id == user.id).all():
        db_session.delete(n)
    db_session.commit()

    # Create 3 unread notifications
    n1 = create_notification(user.id, "Notice 1", "Body 1", "GENERAL", db_session)
    n2 = create_notification(user.id, "Notice 2", "Body 2", "GENERAL", db_session)
    n3 = create_notification(user.id, "Notice 3", "Body 3", "GENERAL", db_session)

    assert get_unread_count(user.id, db_session) == 3

    # Mark single as read
    mark_notification_as_read(n1.id, user.id, db_session)
    assert get_unread_count(user.id, db_session) == 2

    # Mark all remaining as read
    marked_count = mark_all_as_read(user.id, db_session)
    assert marked_count == 2
    assert get_unread_count(user.id, db_session) == 0

    # Delete single notification
    del_res = delete_notification(n3.id, user.id, db_session)
    assert del_res["success"] is True
    assert db_session.query(Notification).filter(Notification.id == n3.id).first() is None

def test_immutable_audit_logging_with_filters(db_session, enterprise_setup):
    admin = enterprise_setup["admin"]

    log1 = log_audit(
        db=db_session,
        user_id=admin.id,
        action="UPDATE",
        resource_type="ATTENDANCE",
        resource_id="404",
        details="Approved manual regularization for late arrival",
        ip_address="10.0.0.15"
    )
    assert log1.id is not None
    assert log1.ip_address == "10.0.0.15"

    log2 = log_audit(
        db=db_session,
        user_id=admin.id,
        action="LOCK",
        resource_type="PAYROLL",
        resource_id="2026-11",
        details="Locked November 2026 payroll",
        ip_address="10.0.0.15"
    )
    assert log2.id is not None

    # Retrieve with filters
    payroll_logs = get_audit_logs(db_session, resource_type="PAYROLL")
    assert payroll_logs.total >= 1
    assert any(l.action == "LOCK" for l in payroll_logs.items)

    action_logs = get_audit_logs(db_session, action="UPDATE")
    assert any(l.resource_type == "ATTENDANCE" for l in action_logs.items)

def test_secure_document_repository(db_session, enterprise_setup, tmp_path):
    emp = enterprise_setup["emp_eng"]

    # 1. Valid PDF file upload
    content = b"%PDF-1.4 test document binary stream content"
    file_obj = UploadFile(
        file=io.BytesIO(content),
        filename="Offer_Letter.pdf",
        headers={"content-type": "application/pdf"}
    )
    doc = upload_document(
        employee_id=emp.id,
        title="Employment Contract Offer Letter",
        document_type="CONTRACT",
        file=file_obj,
        db=db_session
    )
    assert doc.id is not None
    assert doc.mime_type == "application/pdf"
    assert os.path.exists(doc.file_path)

    # 2. Unsupported file type rejected
    bad_file = UploadFile(
        file=io.BytesIO(b"binary executable payload"),
        filename="malware.exe",
        headers={"content-type": "application/x-msdownload"}
    )
    with pytest.raises(HTTPException) as exc:
        upload_document(emp.id, "Malicious file", "OTHER", bad_file, db_session)
    assert exc.value.status_code == 400
    assert "Unsupported file type" in str(exc.value.detail)

    # 3. List documents for employee
    docs = get_employee_documents(emp.id, db_session)
    assert len(docs) >= 1
    assert docs[0].title == "Employment Contract Offer Letter"

    # 4. Delete document cleans up DB and disk file
    f_path = doc.file_path
    del_res = delete_document(doc.id, db_session)
    assert del_res["success"] is True
    assert not os.path.exists(f_path)
    assert db_session.query(EmployeeDocument).filter(EmployeeDocument.id == doc.id).first() is None

def test_multi_format_reports_and_streaming_exports(db_session, enterprise_setup):
    # 1. Employee Report
    h_emp, r_emp, s_emp = generate_employee_report(db_session)
    assert "Employee Code" in h_emp
    assert len(r_emp) >= 2
    assert s_emp["total_employees"] >= 2

    # 2. Department Report
    h_dept, r_dept, s_dept = generate_department_report(db_session)
    assert "Department Name" in h_dept
    assert len(r_dept) >= 2

    # 3. CSV Export
    csv_bytes = export_to_csv(h_emp, r_emp)
    assert "EMP-ENG-1" in csv_bytes
    assert "EMP-SAL-1" in csv_bytes

    # 4. Excel (.xlsx) Export
    excel_stream = export_to_excel(h_emp, r_emp, sheet_name="Workforce")
    assert excel_stream.getbuffer().nbytes > 1000
