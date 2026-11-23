import io
import datetime
import pytest
from fastapi import HTTPException, UploadFile
from app.models.employee import Employee
from app.models.user import User
from app.services import employee_service

def test_avatar_upload_and_approval_lifecycle(db_session):
    # 1. Setup Admin and Employee in DB
    admin = User(
        username="admin_avatar_test",
        email="admin_avatar@company.com",
        hashed_password="fakehash",
        role="ADMIN",
        is_active=True
    )
    db_session.add(admin)
    db_session.flush()

    emp_user = User(
        username="emp_avatar_test",
        email="emp_avatar@company.com",
        hashed_password="fakehash",
        role="EMPLOYEE",
        is_active=True
    )
    db_session.add(emp_user)
    db_session.flush()

    emp = Employee(
        user_id=emp_user.id,
        employee_code="EMP-AV-01",
        full_name="Avatar Tester",
        phone="9998887771",
        hire_date=datetime.date(2026, 1, 1),
        position="Tester",
        salary=60000,
        department_id=1,
        employment_status="ACTIVE",
        profile_picture_status="NONE"
    )
    db_session.add(emp)
    db_session.commit()

    # 2. Test Invalid MIME Type (e.g., text/plain)
    fake_txt = io.BytesIO(b"not an image")
    upload_txt = UploadFile(filename="test.txt", file=fake_txt, headers={"content-type": "text/plain"})
    with pytest.raises(HTTPException) as exc_info:
        employee_service.request_avatar_update(emp_user.id, upload_txt, db_session)
    assert exc_info.value.status_code == 400
    assert "Invalid image type" in exc_info.value.detail

    # 3. Test Valid PNG Upload
    fake_png = io.BytesIO(b"\x89PNG\r\n\x1a\nfakeimagecontent")
    upload_png = UploadFile(filename="photo.png", file=fake_png, headers={"content-type": "image/png"})
    res = employee_service.request_avatar_update(emp_user.id, upload_png, db_session)

    assert res.profile_picture_status == "PENDING"
    assert res.pending_profile_picture is not None
    assert "/uploads/avatars/" in res.pending_profile_picture
    pending_path = res.pending_profile_picture

    # 4. Test Admin Pending Requests Listing
    pending_list = employee_service.get_pending_avatar_requests(db_session)
    matching = [p for p in pending_list if p.employee_id == emp.id]
    assert len(matching) == 1
    assert matching[0].pending_profile_picture == pending_path
    assert matching[0].profile_picture_status == "PENDING"

    # 5. Test Admin Rejection with Reason
    rejected_res = employee_service.review_avatar_request(
        employee_id=emp.id,
        status_decision="REJECTED",
        rejection_reason="Face not clear in the photo",
        admin_user_id=admin.id,
        db=db_session
    )
    assert rejected_res.profile_picture_status == "REJECTED"
    assert rejected_res.profile_picture_rejection_reason == "Face not clear in the photo"
    assert rejected_res.pending_profile_picture is None

    # Verify pending list is now empty for this user
    pending_list_after_rej = employee_service.get_pending_avatar_requests(db_session)
    assert len([p for p in pending_list_after_rej if p.employee_id == emp.id]) == 0

    # 6. Re-upload New Photo
    fake_jpg = io.BytesIO(b"\xff\xd8\xfffakejpegcontent")
    upload_jpg = UploadFile(filename="new_photo.jpg", file=fake_jpg, headers={"content-type": "image/jpeg"})
    res2 = employee_service.request_avatar_update(emp_user.id, upload_jpg, db_session)
    assert res2.profile_picture_status == "PENDING"
    assert res2.pending_profile_picture is not None
    new_pending_path = res2.pending_profile_picture

    # 7. Test Admin Approval
    approved_res = employee_service.review_avatar_request(
        employee_id=emp.id,
        status_decision="APPROVED",
        rejection_reason=None,
        admin_user_id=admin.id,
        db=db_session
    )
    assert approved_res.profile_picture_status == "APPROVED"
    assert approved_res.profile_picture == new_pending_path
    assert approved_res.pending_profile_picture is None
