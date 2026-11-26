from datetime import date
from decimal import Decimal
import pytest
from fastapi import HTTPException

from app.models.user import User
from app.models.department import Department
from app.models.employee import Employee
from app.schemas.department import DepartmentCreate, DepartmentUpdate
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeePatch,
    EmployeeSelfUpdate
)
from app.services.department_service import (
    create_department,
    get_all_departments,
    get_department_by_id,
    update_department,
    get_department_employees,
    reassign_employees,
    delete_department
)
from app.services.employee_service import (
    create_employee,
    get_all_employees,
    get_employee_by_id,
    update_employee,
    patch_employee,
    update_employee_status,
    update_my_profile,
    delete_employee
)
from app.utils.security import hash_password

@pytest.fixture
def sample_department(db_session):
    dept = Department(name="QA Testing", description="Quality assurance and testing")
    db_session.add(dept)
    db_session.commit()
    db_session.refresh(dept)
    return dept

@pytest.fixture
def target_department(db_session):
    dept = Department(name="DevOps", description="Platform infrastructure and cloud")
    db_session.add(dept)
    db_session.commit()
    db_session.refresh(dept)
    return dept

@pytest.fixture
def fresh_user(db_session):
    user = User(
        username="candidate_user",
        email="candidate@ems.com",
        hashed_password=hash_password("Pass123!"),
        role="EMPLOYEE",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

def test_create_and_get_department(db_session):
    dept_data = DepartmentCreate(name="Finance Ops", description="Financial operations")
    dept = create_department(dept_data, db_session)
    assert dept.id is not None
    assert dept.name == "Finance Ops"
    assert dept.employee_count == 0

    fetched = get_department_by_id(dept.id, db_session)
    assert fetched.name == "Finance Ops"

def test_duplicate_department_name_fails(db_session, sample_department):
    dup_data = DepartmentCreate(name=sample_department.name, description="Duplicate")
    with pytest.raises(HTTPException) as exc:
        create_department(dup_data, db_session)
    assert exc.value.status_code == 409

def test_update_department(db_session, sample_department):
    up_data = DepartmentUpdate(name="QA and Automation", description="Updated description")
    updated = update_department(sample_department.id, up_data, db_session)
    assert updated.name == "QA and Automation"
    assert updated.description == "Updated description"

def test_create_employee_auto_code_and_balance(db_session, sample_department, fresh_user):
    emp_data = EmployeeCreate(
        user_id=fresh_user.id,
        department_id=sample_department.id,
        full_name="Sarah Connor",
        phone="+19876543210",
        hire_date=date(2026, 2, 1),
        position="QA Engineer",
        salary=Decimal("70000.00"),
        gender="Female",
        employment_status="ACTIVE"
    )
    emp = create_employee(emp_data, db_session)
    assert emp.id is not None
    assert emp.employee_code.startswith("EMP-")
    assert emp.full_name == "Sarah Connor"
    assert emp.leave_balance is not None
    assert emp.leave_balance.annual_total in (15, 18)

def test_create_employee_duplicate_phone_fails(db_session, sample_department, fresh_user):
    emp_data1 = EmployeeCreate(
        user_id=fresh_user.id,
        department_id=sample_department.id,
        full_name="User One",
        phone="+19999999999",
        hire_date=date(2026, 1, 1),
        position="Tester",
        salary=Decimal("50000.00")
    )
    create_employee(emp_data1, db_session)

    # Second user with same phone
    user2 = User(username="user2", email="u2@ems.com", hashed_password="h", role="EMPLOYEE")
    db_session.add(user2)
    db_session.commit()

    emp_data2 = EmployeeCreate(
        user_id=user2.id,
        department_id=sample_department.id,
        full_name="User Two",
        phone="+19999999999",
        hire_date=date(2026, 1, 1),
        position="Tester",
        salary=Decimal("50000.00")
    )
    with pytest.raises(HTTPException) as exc:
        create_employee(emp_data2, db_session)
    assert exc.value.status_code == 409

def test_get_all_employees_with_search_and_filter(db_session, sample_department, fresh_user):
    emp_data = EmployeeCreate(
        user_id=fresh_user.id,
        department_id=sample_department.id,
        full_name="Unique Searchable Name",
        phone="+18888888888",
        hire_date=date(2026, 1, 1),
        position="Lead Architect",
        salary=Decimal("95000.00"),
        employment_status="ACTIVE"
    )
    create_employee(emp_data, db_session)

    # Search by name
    res = get_all_employees(db_session, search="Searchable")
    assert res.total >= 1
    assert res.items[0].full_name == "Unique Searchable Name"

    # Filter by department
    res_dept = get_all_employees(db_session, department_id=sample_department.id)
    assert res_dept.total >= 1

def test_employee_self_update_profile(db_session, sample_department, fresh_user):
    emp_data = EmployeeCreate(
        user_id=fresh_user.id,
        department_id=sample_department.id,
        full_name="Editable Person",
        phone="+17777777777",
        hire_date=date(2026, 1, 1),
        position="Staff",
        salary=Decimal("60000.00")
    )
    create_employee(emp_data, db_session)

    update_data = EmployeeSelfUpdate(
        phone="+17777777778",
        address="456 Elm Street",
        profile_picture="https://example.com/avatar.jpg"
    )
    updated = update_my_profile(fresh_user.id, update_data, db_session)
    assert updated.phone == "+17777777778"
    assert updated.address == "456 Elm Street"
    assert updated.profile_picture == "https://example.com/avatar.jpg"

def test_update_employee_status(db_session, sample_department, fresh_user):
    emp_data = EmployeeCreate(
        user_id=fresh_user.id,
        department_id=sample_department.id,
        full_name="Status Check",
        phone="+16666666666",
        hire_date=date(2026, 1, 1),
        position="Staff",
        salary=Decimal("60000.00")
    )
    emp = create_employee(emp_data, db_session)

    # Change status to INACTIVE
    updated = update_employee_status(emp.id, "INACTIVE", db_session)
    assert updated.employment_status == "INACTIVE"
    assert updated.user.is_active is False

def test_delete_department_with_employees_safeguard(db_session, sample_department, target_department, fresh_user):
    emp_data = EmployeeCreate(
        user_id=fresh_user.id,
        department_id=sample_department.id,
        full_name="Assigned Worker",
        phone="+15555555555",
        hire_date=date(2026, 1, 1),
        position="Staff",
        salary=Decimal("60000.00")
    )
    emp = create_employee(emp_data, db_session)

    # 1. Attempt delete without reassigning -> should fail
    with pytest.raises(HTTPException) as exc:
        delete_department(sample_department.id, db_session)
    assert exc.value.status_code == 409

    # 2. Reassign to target department and delete -> should succeed
    res = delete_department(sample_department.id, db_session, reassign_to=target_department.id)
    assert res["success"] is True

    # 3. Verify employee was moved to target department
    db_session.refresh(emp)
    assert emp.department_id == target_department.id
