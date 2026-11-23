from typing import Annotated
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.notification import (
    NotificationBroadcast,
    NotificationResponse,
    UnreadCountResponse
)
from app.schemas.common import PaginatedResponse, MessageResponse
from app.services import notification_service
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import get_current_admin

router = APIRouter()

@router.get("/", response_model=PaginatedResponse[NotificationResponse])
def get_my_notifications(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False)
):
    return notification_service.get_user_notifications(
        user_id=current_user.id,
        db=db,
        page=page,
        size=size,
        unread_only=unread_only
    )

@router.get("/unread-count", response_model=UnreadCountResponse)
def get_unread_count(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    count = notification_service.get_unread_count(current_user.id, db)
    return {"unread_count": count}

@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_as_read(
    notification_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    return notification_service.mark_notification_as_read(notification_id, current_user.id, db)

@router.post("/read-all", response_model=MessageResponse)
def mark_all_as_read(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    count = notification_service.mark_all_as_read(current_user.id, db)
    return {"message": f"Marked {count} notifications as read", "success": True}

@router.post("/broadcast", response_model=MessageResponse)
def broadcast_announcement(
    data: NotificationBroadcast,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    count = notification_service.broadcast_notification(data, db)
    return {"message": f"Broadcasted announcement to {count} users", "success": True}

@router.delete("/{notification_id}", response_model=MessageResponse)
def delete_notification(
    notification_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    return notification_service.delete_notification(notification_id, current_user.id, db)
