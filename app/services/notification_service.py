from typing import Optional, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationCreate, NotificationBroadcast, NotificationResponse
from app.schemas.common import PaginatedResponse
from app.utils.pagination import paginate

def create_notification(
    user_id: int,
    title: str,
    message: str,
    type_str: str,
    db: Session
) -> Notification:
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type_str,
        is_read=False
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification

def broadcast_notification(data: NotificationBroadcast, db: Session) -> int:
    query = db.query(User).filter(User.is_active == True)
    if data.target_role:
        query = query.filter(User.role == data.target_role.upper())

    users = query.all()
    count = 0
    try:
        for u in users:
            n = Notification(
                user_id=u.id,
                title=data.title,
                message=data.message,
                type=data.type,
                is_read=False
            )
            db.add(n)
            count += 1
        db.commit()
        return count
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to broadcast notifications: {str(exc)}"
        )

def get_user_notifications(
    user_id: int,
    db: Session,
    page: int = 1,
    size: int = 20,
    unread_only: bool = False
) -> PaginatedResponse[NotificationResponse]:
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        query = query.filter(Notification.is_read == False)
    query = query.order_by(Notification.created_at.desc(), Notification.id.desc())
    return paginate(query, page, size)

def mark_notification_as_read(notification_id: int, user_id: int, db: Session) -> Notification:
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == user_id
    ).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    try:
        notification.is_read = True
        db.commit()
        db.refresh(notification)
        return notification
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update notification: {str(exc)}"
        )

def mark_all_as_read(user_id: int, db: Session) -> int:
    try:
        count = db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).update({"is_read": True})
        db.commit()
        return count
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mark all notifications as read: {str(exc)}"
        )

def get_unread_count(user_id: int, db: Session) -> int:
    return db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False
    ).count()

def delete_notification(notification_id: int, user_id: int, db: Session) -> dict:
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == user_id
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    try:
        db.delete(notification)
        db.commit()
        return {"message": "Notification deleted successfully", "success": True}
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete notification: {str(exc)}"
        )
