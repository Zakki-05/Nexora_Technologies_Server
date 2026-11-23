import os
from typing import Annotated, List
from fastapi import APIRouter, Depends, Form, File, UploadFile, status, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.document import DocumentResponse
from app.schemas.common import MessageResponse
from app.services import document_service
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import get_current_admin

router = APIRouter()

def get_employee_id(current_user: User, db: Session) -> int:
    from app.services.employee_service import ensure_employee_profile
    emp = ensure_employee_profile(current_user, db)
    return emp.id

@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    title: Annotated[str | None, Form()] = None,
    document_type: Annotated[str, Form()] = "OTHER",
    employee_id: Annotated[int | None, Form()] = None
):
    target_emp_id = employee_id
    user_role = current_user.role.strip().upper()

    if target_emp_id is None or user_role == "EMPLOYEE":
        target_emp_id = get_employee_id(current_user, db)

    doc_title = title.strip() if title and title.strip() else (file.filename or "Untitled Document")

    return document_service.upload_document(
        employee_id=target_emp_id,
        title=doc_title,
        document_type=document_type,
        file=file,
        db=db
    )

@router.get("/my-documents", response_model=List[DocumentResponse])
def get_my_documents(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    employee_id = get_employee_id(current_user, db)
    return document_service.get_employee_documents(employee_id, db)

@router.get("/employee/{employee_id}", response_model=List[DocumentResponse])
def get_employee_documents(
    employee_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    user_role = current_user.role.strip().upper()
    if user_role == "EMPLOYEE":
        if not current_user.employee or current_user.employee.id != employee_id:
            raise HTTPException(status_code=403, detail="Access denied")

    return document_service.get_employee_documents(employee_id, db)

@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    doc = document_service.get_document_by_id(document_id, db)
    user_role = current_user.role.strip().upper()

    if user_role == "EMPLOYEE":
        if not current_user.employee or current_user.employee.id != doc.employee_id:
            raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="File on disk not found")

    return FileResponse(
        path=doc.file_path,
        filename=doc.file_name,
        media_type=doc.mime_type
    )

@router.delete("/{document_id}", response_model=MessageResponse)
def delete_document(
    document_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    doc = document_service.get_document_by_id(document_id, db)
    user_role = current_user.role.strip().upper()

    if user_role == "EMPLOYEE":
        if not current_user.employee or current_user.employee.id != doc.employee_id:
            raise HTTPException(status_code=403, detail="Access denied")

    return document_service.delete_document(document_id, db)
