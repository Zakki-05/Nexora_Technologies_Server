import pytest
from fastapi import HTTPException
from app.services import employee_service

def test_get_employees(db_session):
    res = employee_service.get_all_employees(db_session, page=1, size=10)
    assert res.total >= 0

def test_get_employee_not_found(db_session):
    with pytest.raises(HTTPException) as exc_info:
        employee_service.get_employee_by_id(9999, db_session)
    assert exc_info.value.status_code == 404
