import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, get_db
from app.models.user import User
from app.models.department import Department
from app.models.employee import Employee
from app.utils.security import hash_password, create_access_token

TEST_DATABASE_URL = "sqlite://"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine
)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()

@pytest.fixture
def super_admin_user(db_session):
    user = User(
        username="test_super_admin",
        email="superadmin_test@ems.com",
        hashed_password=hash_password("SuperAdmin@123"),
        role="SUPER_ADMIN",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest.fixture
def admin_user(db_session):
    user = User(
        username="test_admin",
        email="admin_test@ems.com",
        hashed_password=hash_password("Admin@123"),
        role="ADMIN",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest.fixture
def employee_user(db_session):
    user = User(
        username="test_employee",
        email="employee_test@ems.com",
        hashed_password=hash_password("Employee@123"),
        role="EMPLOYEE",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest.fixture
def super_admin_token(super_admin_user):
    return create_access_token({"sub": str(super_admin_user.id), "role": super_admin_user.role})

@pytest.fixture
def admin_token(admin_user):
    return create_access_token({"sub": str(admin_user.id), "role": admin_user.role})

@pytest.fixture
def employee_token(employee_user):
    return create_access_token({"sub": str(employee_user.id), "role": employee_user.role})

@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}

@pytest.fixture
def employee_headers(employee_token):
    return {"Authorization": f"Bearer {employee_token}"}
