import pytest
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.models.user import User
from app.models.organization import Organization
from app.models.department import Department
from app.models.employee import Employee
from app.utils.security import hash_password, create_access_token

@pytest.fixture
def v2_client(client):
    return client

@pytest.fixture
def v2_seed(db_session):
    org = Organization(
        id=1,
        name="Nexora Technologies Inc.",
        slug="nexora-tech",
        company_code="NEX-001",
        subscription_plan="ENTERPRISE",
        is_active=True
    )
    db_session.add(org)
    dept = Department(name="Engineering", description="Core Engineering", organization_id=1)
    db_session.add(dept)
    db_session.flush()

    admin_user = User(
        username="v2_admin",
        email="v2_admin@nexora.tech",
        hashed_password=hash_password("StrongAdminPass!99"),
        role="ADMIN",
        organization_id=1,
        is_active=True
    )
    emp_user = User(
        username="v2_emp",
        email="v2_emp@nexora.tech",
        hashed_password=hash_password("StrongEmpPass!99"),
        role="EMPLOYEE",
        organization_id=1,
        is_active=True
    )
    db_session.add_all([admin_user, emp_user])
    db_session.flush()

    admin_emp = Employee(
        employee_code="EMP-9001",
        full_name="V2 Admin",
        phone="9000000001",
        hire_date=date(2025, 1, 1),
        position="Engineering Lead",
        salary=Decimal("120000.00"),
        department_id=dept.id,
        user_id=admin_user.id,
        organization_id=1
    )
    regular_emp = Employee(
        employee_code="EMP-9002",
        full_name="V2 Employee",
        phone="9000000002",
        hire_date=date(2025, 1, 1),
        position="Software Engineer",
        salary=Decimal("80000.00"),
        department_id=dept.id,
        user_id=emp_user.id,
        organization_id=1
    )
    db_session.add_all([admin_emp, regular_emp])
    db_session.commit()
    return {"admin": admin_user, "employee": emp_user, "org": org}

def test_security_strict_password_no_backdoor(v2_client, v2_seed):
    # Attempting common/demo passwords with "123" or "admin" MUST fail with 401
    for bad_pwd in ["Employee@123", "Admin@123", "admin123", "123456"]:
        res = v2_client.post("/auth/login", json={
            "email": "v2_admin@nexora.tech",
            "password": bad_pwd
        })
        assert res.status_code == 401

def test_refresh_token_rotation_flow(v2_client, v2_seed):
    login_res = v2_client.post("/auth/login", json={
        "email": "v2_emp@nexora.tech",
        "password": "StrongEmpPass!99"
    })
    assert login_res.status_code == 200
    data = login_res.json()
    assert "access_token" in data
    assert "refresh_token" in data

    refresh_res = v2_client.post("/auth/refresh", json={
        "refresh_token": data["refresh_token"]
    })
    assert refresh_res.status_code == 200
    refreshed = refresh_res.json()
    assert "access_token" in refreshed
    assert "refresh_token" in refreshed

    # Using access token as refresh token must fail
    bad_res = v2_client.post("/auth/refresh", json={
        "refresh_token": data["access_token"]
    })
    assert bad_res.status_code == 401

def test_expense_claims_rbac_and_lifecycle(v2_client, v2_seed):
    emp_token = create_access_token({"sub": str(v2_seed["employee"].id), "role": "EMPLOYEE"})
    admin_token = create_access_token({"sub": str(v2_seed["admin"].id), "role": "ADMIN"})

    # 1. Employee submits expense claim
    create_res = v2_client.post(
        "/expenses",
        headers={"Authorization": f"Bearer {emp_token}"},
        json={
            "title": "Monitor Stand",
            "category": "HARDWARE",
            "amount": 2500.00,
            "expense_date": "2026-11-26",
            "notes": "Ergonomic stand"
        }
    )
    assert create_res.status_code == 201
    claim_id = create_res.json()["id"]
    assert create_res.json()["status"] == "PENDING"

    # 2. Employee CANNOT approve own claim (403 Forbidden)
    forbidden_res = v2_client.patch(
        f"/expenses/{claim_id}/review",
        headers={"Authorization": f"Bearer {emp_token}"},
        json={"status": "APPROVED", "approved_amount": 2500.00}
    )
    assert forbidden_res.status_code == 403

    # 3. Admin approves claim
    approve_res = v2_client.patch(
        f"/expenses/{claim_id}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "APPROVED", "approved_amount": 2500.00, "remarks": "Approved"}
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "APPROVED"

    # 4. Employee cannot delete already reviewed claim
    del_res = v2_client.delete(
        f"/expenses/{claim_id}",
        headers={"Authorization": f"Bearer {emp_token}"}
    )
    assert del_res.status_code == 400

def test_organization_and_subscription_endpoints(v2_client, v2_seed):
    emp_token = create_access_token({"sub": str(v2_seed["employee"].id), "role": "EMPLOYEE"})

    org_res = v2_client.get("/organizations/current", headers={"Authorization": f"Bearer {emp_token}"})
    assert org_res.status_code == 200
    assert org_res.json()["company_code"] == "NEX-001"

    plans_res = v2_client.get("/organizations/subscription/plans")
    assert plans_res.status_code == 200
    assert len(plans_res.json()["plans"]) == 4

    sub_res = v2_client.get("/organizations/current/subscription", headers={"Authorization": f"Bearer {emp_token}"})
    assert sub_res.status_code == 200
    assert sub_res.json()["subscription_plan"] == "ENTERPRISE"
    assert sub_res.json()["usage"]["current_employees"] == 2

def test_security_headers_present(v2_client):
    res = v2_client.get("/")
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
