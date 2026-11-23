from typing import Annotated, Optional
from fastapi import APIRouter, Depends, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    UserLogin,
    UserRegister,
    UserResponse,
    Token,
    PasswordChange,
    UserStatusUpdate,
    UserRoleUpdate
)
from app.schemas.common import MessageResponse, PaginatedResponse
from app.services import auth_service
from app.dependencies.auth import get_current_user, get_optional_current_user
from app.dependencies.permissions import get_current_admin, get_current_super_admin

router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    data: UserRegister,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)] = None
):
    return auth_service.register_user(data, db, current_user)
@router.post("/login", response_model=Token)
def login(
    data: UserLogin,
    db: Annotated[Session, Depends(get_db)]
):
    return auth_service.login_user(data, db)

@router.post("/token", response_model=Token)
def token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_db)],
):
    return auth_service.login_user(
        UserLogin(email=form_data.username, password=form_data.password),
        db,
    )

@router.get("/me", response_model=UserResponse)
def get_profile(
    current_user: Annotated[User, Depends(get_current_user)]
):
    return current_user

@router.post("/change-password", response_model=MessageResponse)
def change_password(
    data: PasswordChange,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)]
):
    return auth_service.change_password(current_user.id, data, db)

@router.post("/logout", response_model=MessageResponse)
def logout(
    current_user: Annotated[User, Depends(get_current_user)]
):
    return {"message": "Logged out successfully", "success": True}

@router.get("/users", response_model=PaginatedResponse[UserResponse])
def get_users(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None
):
    return auth_service.get_all_users(db, page, size, role, is_active, search)

@router.patch("/users/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: int,
    data: UserStatusUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)]
):
    return auth_service.update_user_status(user_id, data.is_active, db, admin)

@router.patch("/users/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    db: Annotated[Session, Depends(get_db)],
    super_admin: Annotated[User, Depends(get_current_super_admin)]
):
    return auth_service.update_user_role(user_id, data.role, db, super_admin)
