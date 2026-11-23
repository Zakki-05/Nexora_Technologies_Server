from datetime import date
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Department, Employee, User
from app.schemas.employee import EmployeeCreate, EmployeeResponse
from app.services.employee_service import create_employee

def test_create_employee_maps_schema_fields_to_model():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine)

    try:
        with test_session() as db:
            user = User(
                username="employee-check",
                email="employee-check@example.com",
                hashed_password="test-hash",
                role="EMPLOYEE",
            )
            department = Department(name="Engineering")
            db.add_all([user, department])
            db.commit()
            db.refresh(user)
            db.refresh(department)

            data = EmployeeCreate(
                full_name="Test Employee",
                phone="+12345678901",
                hire_date=date(2026, 1, 1),
                position="Developer",
                salary=Decimal("50000"),
                department_id=department.id,
                user_id=user.id,
            )

            employee = create_employee(data, db)
            response = EmployeeResponse.model_validate(employee)

            assert response.full_name == "Test Employee"
            assert response.phone == "+12345678901"
            assert response.position == "Developer"
    finally:
        engine.dispose()
