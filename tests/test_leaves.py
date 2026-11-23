import pytest
from fastapi import HTTPException
from app.services import leave_service

def test_get_leaves(db_session):
    res = leave_service.get_all_leaves(db_session, page=1, size=10)
    assert res.total >= 0

def test_get_leave_not_found(db_session):
    with pytest.raises(HTTPException) as exc_info:
        leave_service.delete_leave(9999, db_session)
    assert exc_info.value.status_code == 404
