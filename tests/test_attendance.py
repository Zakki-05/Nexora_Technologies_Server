import pytest
from app.services import attendance_service

def test_attendance_listing(db_session):
    res = attendance_service.get_all_attendance(db_session, page=1, size=10)
    assert res.total >= 0
