from datetime import date
from typing import Annotated, Optional, Literal
from fastapi import APIRouter, Depends, Query, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services import report_service
from app.dependencies.permissions import get_current_admin

router = APIRouter()

@router.get("/employees")
def get_employee_report(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    department_id: Optional[int] = None,
    employment_status: Optional[str] = None
):
    headers, rows, summary = report_service.generate_employee_report(
        db, department_id, employment_status
    )
    return {"headers": headers, "rows": rows, "summary": summary}

@router.get("/departments")
def get_department_report(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    headers, rows, summary = report_service.generate_department_report(db)
    return {"headers": headers, "rows": rows, "summary": summary}

@router.get("/attendance")
def get_attendance_report(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    department_id: Optional[int] = None,
    employee_id: Optional[int] = None
):
    headers, rows, summary = report_service.generate_attendance_report(
        db, start_date, end_date, department_id, employee_id
    )
    return {"headers": headers, "rows": rows, "summary": summary}

@router.get("/leaves")
def get_leave_report(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status_filter: Optional[str] = None,
    employee_id: Optional[int] = None
):
    headers, rows, summary = report_service.generate_leave_report(
        db, start_date, end_date, status_filter, employee_id
    )
    return {"headers": headers, "rows": rows, "summary": summary}

@router.get("/salaries")
def get_salary_report(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    year: Optional[int] = None,
    month: Annotated[Optional[int], Query(ge=1, le=12)] = None,
    department_id: Optional[int] = None
):
    headers, rows, summary = report_service.generate_salary_report(
        db, year, month, department_id
    )
    return {"headers": headers, "rows": rows, "summary": summary}

def get_report_data(
    report_type: str,
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    department_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    year: Optional[int] = None,
    month: Optional[int] = None
):
    normalized_type = report_type.strip().lower()
    if normalized_type == "employees":
        return report_service.generate_employee_report(db, department_id)
    elif normalized_type == "departments":
        return report_service.generate_department_report(db)
    elif normalized_type == "attendance":
        return report_service.generate_attendance_report(db, start_date, end_date, department_id, employee_id)
    elif normalized_type == "leaves":
        return report_service.generate_leave_report(db, start_date, end_date, None, employee_id)
    elif normalized_type == "salaries":
        return report_service.generate_salary_report(db, year, month, department_id)
    else:
        raise HTTPException(status_code=400, detail=f"Invalid report type: '{report_type}'")

@router.get("/export/csv")
def export_csv(
    report_type: Literal["employees", "departments", "attendance", "leaves", "salaries"],
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    department_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    year: Optional[int] = None,
    month: Optional[int] = None
):
    headers, rows, _ = get_report_data(
        report_type, db, start_date, end_date, department_id, employee_id, year, month
    )
    csv_content = report_service.export_to_csv(headers, rows)

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={report_type}_report.csv"}
    )

@router.get("/export/excel")
def export_excel(
    report_type: Literal["employees", "departments", "attendance", "leaves", "salaries"],
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    department_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    year: Optional[int] = None,
    month: Optional[int] = None
):
    headers, rows, _ = get_report_data(
        report_type, db, start_date, end_date, department_id, employee_id, year, month
    )
    xlsx_stream = report_service.export_to_excel(headers, rows, sheet_name=report_type.capitalize())

    return StreamingResponse(
        xlsx_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={report_type}_report.xlsx"}
    )
