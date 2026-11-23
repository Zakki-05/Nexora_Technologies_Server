from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.models.audit_log import AuditLog
from app.schemas.audit_log import AuditLogResponse
from app.schemas.common import PaginatedResponse
from app.utils.pagination import paginate

def log_audit(
    db: Session,
    user_id: Optional[int],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None
) -> AuditLog:
    try:
        log_entry = AuditLog(
            user_id=user_id,
            action=action.upper(),
            resource_type=resource_type.upper(),
            resource_id=str(resource_id) if resource_id is not None else None,
            details=details,
            ip_address=ip_address
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry
    except Exception:
        db.rollback()
        # Logging failures should never crash primary application operations
        pass

def get_audit_logs(
    db: Session,
    page: int = 1,
    size: int = 50,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> PaginatedResponse[AuditLogResponse]:
    query = db.query(AuditLog).options(joinedload(AuditLog.user))

    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action.upper())
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type.upper())
    if start_date:
        query = query.filter(AuditLog.created_at >= start_date)
    if end_date:
        query = query.filter(AuditLog.created_at <= end_date)

    query = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    return paginate(query, page, size)
