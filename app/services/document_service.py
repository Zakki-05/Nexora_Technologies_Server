import os
import uuid
import shutil
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, UploadFile, status

from app.models.document import EmployeeDocument
from app.models.employee import Employee
from app.schemas.document import DocumentResponse

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/tmp/uploads" if os.environ.get("VERCEL") else os.path.join(os.getcwd(), "uploads"))
UPLOAD_DIR = os.path.join(UPLOAD_DIR, "documents")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain"
}

def ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)

def upload_document(
    employee_id: int,
    title: str,
    document_type: str,
    file: UploadFile,
    db: Session
) -> EmployeeDocument:
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{content_type}'. Allowed types: PDF, JPG, PNG, DOC, DOCX, TXT."
        )

    ensure_upload_dir()

    # Generate safe unique filename
    ext = os.path.splitext(file.filename or "")[1]
    safe_filename = f"{uuid.uuid4()}{ext}"
    dest_path = os.path.join(UPLOAD_DIR, safe_filename)

    file_size = 0
    try:
        with open(dest_path, "wb") as buffer:
            while chunk := file.file.read(1024 * 64):
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    buffer.close()
                    os.remove(dest_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File size exceeds maximum allowed limit of 10 MB"
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(exc)}"
        )

    try:
        doc = EmployeeDocument(
            employee_id=employee_id,
            title=title.strip(),
            document_type=document_type.upper(),
            file_name=file.filename or "unknown",
            file_path=dest_path,
            file_size=file_size,
            mime_type=content_type
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc
    except Exception as exc:
        db.rollback()
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record document metadata: {str(exc)}"
        )

def get_employee_documents(employee_id: int, db: Session) -> List[EmployeeDocument]:
    return db.query(EmployeeDocument).filter(
        EmployeeDocument.employee_id == employee_id
    ).order_by(EmployeeDocument.uploaded_at.desc()).all()

def get_document_by_id(document_id: int, db: Session) -> EmployeeDocument:
    doc = db.query(EmployeeDocument).filter(EmployeeDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc

def delete_document(document_id: int, db: Session) -> dict:
    doc = get_document_by_id(document_id, db)
    file_path = doc.file_path

    try:
        db.delete(doc)
        db.commit()
        if os.path.exists(file_path):
            os.remove(file_path)
        return {"message": "Document deleted successfully", "success": True}
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(exc)}"
        )
