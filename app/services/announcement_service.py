from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, desc, case
from fastapi import HTTPException, status

from app.models.announcement import Announcement
from app.models.user import User
from app.models.employee import Employee
from app.models.department import Department
from app.models.notification import Notification
from app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementUpdate,
    AnnouncementResponse
)
from app.schemas.common import PaginatedResponse
from app.utils.pagination import paginate
from app.services.audit_service import log_audit

def create_announcement(
    data: AnnouncementCreate,
    author_user_id: int,
    db: Session,
    ip_address: Optional[str] = None
) -> Announcement:
    """
    Creates an organization-wide or department/role-targeted announcement.
    Optionally broadcasts instant notifications to targeted users.
    """
    if data.target_type == "DEPARTMENT" and not data.target_department_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_department_id is required when target_type is DEPARTMENT"
        )
    if data.target_type == "ROLE" and not data.target_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_role is required when target_type is ROLE"
        )

    try:
        announcement = Announcement(
            title=data.title.strip(),
            message=data.message.strip(),
            priority=data.priority.upper(),
            target_type=data.target_type.upper(),
            target_department_id=data.target_department_id,
            target_role=data.target_role.upper() if data.target_role else None,
            expires_at=data.expires_at,
            is_active=data.is_active,
            created_by=author_user_id
        )
        db.add(announcement)
        db.commit()
        db.refresh(announcement)

        # Broadcast notifications to targeted users if requested
        if data.broadcast_notification and data.is_active:
            user_query = db.query(User).filter(User.is_active == True)
            if data.target_type == "DEPARTMENT" and data.target_department_id:
                user_query = user_query.join(Employee, Employee.user_id == User.id).filter(
                    Employee.department_id == data.target_department_id
                )
            elif data.target_type == "ROLE" and data.target_role:
                user_query = user_query.filter(User.role == data.target_role.upper())

            target_users = user_query.all()
            for u in target_users:
                n = Notification(
                    user_id=u.id,
                    title=f"[{data.priority}] {data.title}",
                    message=data.message[:250],
                    type="ANNOUNCEMENT",
                    is_read=False
                )
                db.add(n)
            db.commit()

        log_audit(
            db=db,
            user_id=author_user_id,
            action="CREATE",
            resource_type="ANNOUNCEMENT",
            resource_id=str(announcement.id),
            details=f"Created {data.priority} announcement: '{data.title}'",
            ip_address=ip_address
        )

        return announcement
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create announcement: {str(exc)}"
        )

def get_announcements_for_user(
    user: User,
    db: Session,
    page: int = 1,
    size: int = 20,
    active_only: bool = True
) -> PaginatedResponse[AnnouncementResponse]:
    """
    Returns announcements accessible by the user:
    - Admins see all announcements.
    - Employees see announcements targeting ALL, their DEPARTMENT, or their ROLE,
      filtering out expired or inactive announcements.
    """
    query = db.query(Announcement).options(
        joinedload(Announcement.author),
        joinedload(Announcement.department)
    )

    now = datetime.now()
    user_role = user.role.strip().upper()

    if user_role not in ["ADMIN", "SUPER_ADMIN"]:
        # Employee view: only active & unexpired
        query = query.filter(Announcement.is_active == True)
        query = query.filter(
            or_(
                Announcement.expires_at == None,
                Announcement.expires_at >= now
            )
        )

        user_dept_id = user.employee.department_id if user.employee else None
        target_conditions = [Announcement.target_type == "ALL"]
        if user_dept_id:
            target_conditions.append(
                (Announcement.target_type == "DEPARTMENT") &
                (Announcement.target_department_id == user_dept_id)
            )
        target_conditions.append(
            (Announcement.target_type == "ROLE") &
            (Announcement.target_role == user_role)
        )
        query = query.filter(or_(*target_conditions))

    elif active_only:
        query = query.filter(Announcement.is_active == True)

    # Order priority: URGENT -> HIGH -> NORMAL, then newest
    priority_order = case(
        (Announcement.priority == "URGENT", 1),
        (Announcement.priority == "HIGH", 2),
        else_=3
    )
    query = query.order_by(priority_order, Announcement.created_at.desc(), Announcement.id.desc())

    paginated = paginate(query, page, size)

    items: List[AnnouncementResponse] = []
    for a in paginated.items:
        items.append(AnnouncementResponse(
            id=a.id,
            title=a.title,
            message=a.message,
            priority=a.priority,
            target_type=a.target_type,
            target_department_id=a.target_department_id,
            target_department_name=a.department.name if a.department else None,
            target_role=a.target_role,
            expires_at=a.expires_at,
            is_active=a.is_active,
            created_by=a.created_by,
            author_name=a.author.username if a.author else None,
            created_at=a.created_at,
            updated_at=a.updated_at
        ))

    return PaginatedResponse[AnnouncementResponse](
        items=items,
        total=paginated.total,
        page=paginated.page,
        size=paginated.size,
        pages=paginated.pages
    )

def get_announcement_by_id(announcement_id: int, db: Session) -> Announcement:
    a = db.query(Announcement).options(
        joinedload(Announcement.author),
        joinedload(Announcement.department)
    ).filter(Announcement.id == announcement_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return a

def update_announcement(
    announcement_id: int,
    data: AnnouncementUpdate,
    admin_user_id: int,
    db: Session,
    ip_address: Optional[str] = None
) -> Announcement:
    a = get_announcement_by_id(announcement_id, db)
    update_data = data.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        if key in ["priority", "target_type", "target_role"] and value:
            value = value.upper()
        setattr(a, key, value)

    try:
        db.commit()
        db.refresh(a)
        log_audit(
            db=db,
            user_id=admin_user_id,
            action="UPDATE",
            resource_type="ANNOUNCEMENT",
            resource_id=str(a.id),
            details=f"Updated announcement '{a.title}'",
            ip_address=ip_address
        )
        return a
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update announcement: {str(exc)}"
        )

def delete_announcement(
    announcement_id: int,
    admin_user_id: int,
    db: Session,
    ip_address: Optional[str] = None
) -> dict:
    a = get_announcement_by_id(announcement_id, db)
    try:
        db.delete(a)
        db.commit()
        log_audit(
            db=db,
            user_id=admin_user_id,
            action="DELETE",
            resource_type="ANNOUNCEMENT",
            resource_id=str(announcement_id),
            details=f"Deleted announcement #{announcement_id}",
            ip_address=ip_address
        )
        return {"message": "Announcement deleted successfully", "success": True}
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete announcement: {str(exc)}"
        )
