import pytest
from fastapi import HTTPException
from app.models.user import User
from app.schemas.auth import UserRegister, UserLogin, PasswordChange
from app.services.auth_service import (
    register_user,
    login_user,
    change_password,
    get_all_users,
    update_user_status,
    update_user_role
)
from app.dependencies.permissions import require_roles, require_super_admin_only

def test_register_employee_user(db_session):
    data = UserRegister(
        username="john_emp",
        email="john_emp@ems.com",
        password="ValidPassword123",
        role="EMPLOYEE"
    )
    user = register_user(data, db_session)
    assert user.id is not None
    assert user.username == "john_emp"
    assert user.email == "john_emp@ems.com"
    assert user.role == "EMPLOYEE"
    assert user.is_active is True

def test_register_duplicate_email_raises_conflict(db_session):
    data1 = UserRegister(
        username="unique_1",
        email="duplicate@ems.com",
        password="ValidPassword123",
        role="EMPLOYEE"
    )
    register_user(data1, db_session)

    data2 = UserRegister(
        username="unique_2",
        email="duplicate@ems.com",
        password="ValidPassword123",
        role="EMPLOYEE"
    )
    with pytest.raises(HTTPException) as exc_info:
        register_user(data2, db_session)
    assert exc_info.value.status_code == 409

def test_register_admin_without_super_admin_fails(db_session):
    data = UserRegister(
        username="fake_admin",
        email="fake_admin@ems.com",
        password="ValidPassword123",
        role="ADMIN"
    )
    with pytest.raises(HTTPException) as exc_info:
        register_user(data, db_session, current_user=None)
    assert exc_info.value.status_code == 403

def test_register_admin_with_super_admin_succeeds(db_session, super_admin_user):
    data = UserRegister(
        username="legit_admin",
        email="legit_admin@ems.com",
        password="ValidPassword123",
        role="ADMIN"
    )
    admin = register_user(data, db_session, current_user=super_admin_user)
    assert admin.id is not None
    assert admin.role == "ADMIN"

def test_login_user_success(db_session, employee_user):
    data = UserLogin(email=employee_user.email, password="Employee@123")
    res = login_user(data, db_session)
    assert "access_token" in res
    assert res["token_type"] == "bearer"
    assert res["user"].id == employee_user.id

def test_login_user_wrong_password_fails(db_session, employee_user):
    data = UserLogin(email=employee_user.email, password="WrongPassword!")
    with pytest.raises(HTTPException) as exc_info:
        login_user(data, db_session)
    assert exc_info.value.status_code == 401

def test_login_deactivated_user_fails(db_session, employee_user):
    employee_user.is_active = False
    db_session.commit()

    data = UserLogin(email=employee_user.email, password="Employee@123")
    with pytest.raises(HTTPException) as exc_info:
        login_user(data, db_session)
    assert exc_info.value.status_code == 403

def test_change_password_success_and_failure(db_session, employee_user):
    # 1. Correct change
    data = PasswordChange(
        current_password="Employee@123",
        new_password="NewSecurePassword@123"
    )
    res = change_password(employee_user.id, data, db_session)
    assert res["success"] is True

    # 2. Login with new password
    login_res = login_user(UserLogin(email=employee_user.email, password="NewSecurePassword@123"), db_session)
    assert "access_token" in login_res

    # 3. Old password fails
    with pytest.raises(HTTPException):
        login_user(UserLogin(email=employee_user.email, password="Employee@123"), db_session)

    # 4. Incorrect current password during change
    fail_data = PasswordChange(
        current_password="WrongCurrentPassword",
        new_password="AnotherPassword@123"
    )
    with pytest.raises(HTTPException) as exc_info:
        change_password(employee_user.id, fail_data, db_session)
    assert exc_info.value.status_code == 400

def test_get_all_users_pagination_and_filter(db_session, super_admin_user, admin_user, employee_user):
    res = get_all_users(db_session, page=1, size=2)
    assert res.total >= 3
    assert len(res.items) == 2
    assert res.pages >= 2

    # Filter by role
    admin_res = get_all_users(db_session, role="ADMIN")
    assert all(u.role == "ADMIN" for u in admin_res.items)

def test_update_user_status(db_session, super_admin_user, employee_user):
    # Deactivate employee
    updated = update_user_status(employee_user.id, False, db_session, super_admin_user)
    assert updated.is_active is False

    # Cannot deactivate self
    with pytest.raises(HTTPException) as exc_info:
        update_user_status(super_admin_user.id, False, db_session, super_admin_user)
    assert exc_info.value.status_code == 400

def test_update_user_role(db_session, super_admin_user, employee_user):
    updated = update_user_role(employee_user.id, "ADMIN", db_session, super_admin_user)
    assert updated.role == "ADMIN"

    # Non-super admin cannot change role
    with pytest.raises(HTTPException) as exc_info:
        update_user_role(employee_user.id, "EMPLOYEE", db_session, employee_user)
    assert exc_info.value.status_code == 403

def test_permissions_role_checkers(super_admin_user, admin_user, employee_user):
    admin_checker = require_roles("ADMIN")
    super_admin_checker = require_super_admin_only()

    # Super admin passes admin checker
    assert admin_checker(super_admin_user) == super_admin_user

    # Admin passes admin checker
    assert admin_checker(admin_user) == admin_user

    # Employee fails admin checker
    with pytest.raises(HTTPException) as exc:
        admin_checker(employee_user)
    assert exc.value.status_code == 403

    # Admin fails super admin checker
    with pytest.raises(HTTPException) as exc:
        super_admin_checker(admin_user)
    assert exc.value.status_code == 403

    # Super admin passes super admin checker
    assert super_admin_checker(super_admin_user) == super_admin_user
