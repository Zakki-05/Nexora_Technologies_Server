import pytest
from fastapi import HTTPException
from app.services import department_service

def test_get_departments(db_session):
    res = department_service.get_all_departments(db_session, page=1, size=10)
    assert res.total >= 0

def test_get_department_not_found(db_session):
    with pytest.raises(HTTPException) as exc_info:
        department_service.get_department_by_id(9999, db_session)
    assert exc_info.value.status_code == 404
