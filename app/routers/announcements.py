from typing import Annotated, Optional
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementUpdate,
    AnnouncementResponse
)
from app.schemas.common import PaginatedResponse, MessageResponse
from app.services import announcement_service
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import get_current_admin

router = APIRouter()

def get_client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None

@router.get("/", response_model=PaginatedResponse[AnnouncementResponse])
def get_announcements(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    active_only: bool = Query(True)
):
    """
    List announcements for current user.
    Employees receive notices targeted to ALL, their department, or their role.
    Admins can view all corporate announcements.
    """
    return announcement_service.get_announcements_for_user(
        user=current_user,
        db=db,
        page=page,
        size=size,
        active_only=active_only
    )

@router.post("/", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
def create_announcement(
    data: AnnouncementCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    """Publish an announcement with priority, targeting, and instant notification broadcast."""
    ip = get_client_ip(request)
    announcement = announcement_service.create_announcement(
        data=data,
        author_user_id=admin.id,
        db=db,
        ip_address=ip
    )
    return announcement_service.get_announcement_by_id(announcement.id, db)

@router.get("/{announcement_id}", response_model=AnnouncementResponse)
def get_announcement_detail(
    announcement_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Retrieve details of a single announcement."""
    return announcement_service.get_announcement_by_id(announcement_id, db)

@router.patch("/{announcement_id}", response_model=AnnouncementResponse)
@router.put("/{announcement_id}", response_model=AnnouncementResponse)
def update_announcement(
    announcement_id: int,
    data: AnnouncementUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    """Update announcement title, message, priority, or audience targeting."""
    ip = get_client_ip(request)
    announcement_service.update_announcement(
        announcement_id=announcement_id,
        data=data,
        admin_user_id=admin.id,
        db=db,
        ip_address=ip
    )
    return announcement_service.get_announcement_by_id(announcement_id, db)

@router.delete("/{announcement_id}", response_model=MessageResponse)
def delete_announcement(
    announcement_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    """Delete an announcement (Admin/SuperAdmin only)."""
    ip = get_client_ip(request)
    return announcement_service.delete_announcement(
        announcement_id=announcement_id,
        admin_user_id=admin.id,
        db=db,
        ip_address=ip
    )
