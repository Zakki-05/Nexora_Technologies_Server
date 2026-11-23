import pytest
from fastapi import HTTPException
from app.services import auth_service
from app.schemas.auth import UserCreate, UserLogin
from app.models.user import User
from app.utils.security import hash_password, verify_password

def test_register_user_endpoint_logic(db_session):
    data = UserCreate(
        username="new_auth_user",
        email="new_auth_user@example.com",
        password="SecretPassword123",
        role="EMPLOYEE"
    )
    user = auth_service.register_user(data, db_session)
    assert user.id is not None
    assert user.email == "new_auth_user@example.com"
    assert verify_password("SecretPassword123", user.hashed_password)

def test_register_duplicate_fails(db_session):
    data = UserCreate(
        username="dup_auth_user",
        email="dup_auth_user@example.com",
        password="SecretPassword123",
        role="EMPLOYEE"
    )
    auth_service.register_user(data, db_session)
    with pytest.raises(HTTPException) as exc:
        auth_service.register_user(data, db_session)
    assert exc.value.status_code == 409

def test_auth_login_flow(db_session):
    user = User(
        username="login_user",
        email="login_user@example.com",
        hashed_password=hash_password("Password@123"),
        role="EMPLOYEE",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    # Success
    res = auth_service.login_user(
        UserLogin(email="login_user@example.com", password="Password@123"),
        db_session
    )
    assert "access_token" in res
    assert res["user"].email == user.email

    # Failure
    with pytest.raises(HTTPException) as exc:
        auth_service.login_user(
            UserLogin(email="login_user@example.com", password="WrongPassword"),
            db_session
        )
    assert exc.value.status_code == 401
