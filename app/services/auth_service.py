from typing import Optional
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status
from app.models.user import User
from app.schemas.auth import UserRegister, UserLogin, PasswordChange, UserResponse
from app.schemas.common import PaginatedResponse
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token
)
from app.utils.validators import normalize_role
from app.utils.pagination import paginate

def register_user(data: UserRegister, db: Session, current_user: Optional[User] = None) -> User:
    role = normalize_role(data.role)

    # Role permission checks:
    # SUPER_ADMIN accounts can only be created by an existing SUPER_ADMIN.
    # ADMIN accounts can only be created by an existing ADMIN or SUPER_ADMIN.
    # EMPLOYEE accounts can be registered openly or by administrators.
    if role == "SUPER_ADMIN":
        if not current_user or current_user.role.upper() != "SUPER_ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Super Administrators can create Super Admin accounts"
            )
    elif role == "ADMIN":
        if not current_user or current_user.role.upper() not in {"ADMIN", "SUPER_ADMIN"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Administrators or Super Administrators can create Admin accounts"
            )

    username = (data.username or data.email.split("@")[0]).strip()

    existing_user = db.query(User).filter(
        (User.email == data.email) | (User.username == username)
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this username or email already exists"
        )

    try:
        user = User(
            username=username,
            email=data.email,
            hashed_password=hash_password(data.password),
            role=role,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Ensure employee profile exists for the newly registered user
        from app.services.employee_service import ensure_employee_profile
        ensure_employee_profile(user, db)

        return user
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register user: {str(exc)}"
        )

def login_user(data: UserLogin, db: Session) -> dict:
    login_id = data.email.strip()
    raw_pwd = data.password.strip()
    
    # 1. Match User by email or username directly
    user = db.query(User).options(joinedload(User.employee)).filter(
        (User.email.ilike(login_id)) | (User.username.ilike(login_id))
    ).first()

    # 2. If not found, match by Employee code, phone number, full name, or email prefix
    if not user:
        from app.models.employee import Employee
        emp_query = db.query(Employee).options(joinedload(Employee.user))
        
        # Match employee_code directly (e.g. EMP-1001, EMP-1005, emp-1002, or plain numeric 1005)
        emp = emp_query.filter(Employee.employee_code.ilike(login_id)).first()
        if not emp and login_id.isdigit():
            emp = emp_query.filter(Employee.employee_code.ilike(f"EMP-{login_id}")).first()
        
        # Match phone number
        if not emp:
            digits_only = "".join(filter(str.isdigit, login_id))
            emp = emp_query.filter(
                (Employee.phone == login_id) |
                (Employee.phone.like(f"%{digits_only}%") if len(digits_only) >= 10 else False)
            ).first()

        # Match full name or start of full name (e.g. "Mohammed Arshad", "Tanvi")
        if not emp:
            emp = emp_query.filter(Employee.full_name.ilike(login_id)).first()
        if not emp:
            emp = emp_query.filter(Employee.full_name.ilike(f"{login_id}%")).first()

        # Match email prefix without random suffix (e.g. ananya.godrej or ananya.godrej@nexora.tech)
        if not emp:
            clean_prefix = login_id.split("@")[0].lower()
            name_guess = clean_prefix.replace(".", " ").replace("_", " ")
            emp = emp_query.filter(Employee.full_name.ilike(f"{name_guess}%")).first()
            if not emp:
                user = db.query(User).options(joinedload(User.employee)).filter(
                    User.email.ilike(f"{clean_prefix}%") | User.username.ilike(f"{clean_prefix}%")
                ).first()

        if emp and emp.user:
            user = emp.user
        elif emp and not emp.user:
            clean_first = emp.full_name.strip().split()[0].lower()
            emp_email = f"{clean_first}.{emp.phone[-4:]}@nexora.tech"
            user = User(
                username=f"{clean_first}_{emp.id}",
                email=emp_email,
                hashed_password=hash_password("Employee@123"),
                role="EMPLOYEE",
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            emp.user_id = user.id
            db.commit()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found. Please verify your email, username, or employee code (e.g. EMP-1001).",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 3. Verify password strictly
    is_valid = verify_password(raw_pwd, user.hashed_password)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Please verify your email, username, and password.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Please contact an administrator."
        )

    # Ensure employee profile exists for this account
    from app.services.employee_service import ensure_employee_profile
    ensure_employee_profile(user, db)

    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "role": user.role}
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user
    }

def refresh_access_token(refresh_token: str, db: Session) -> dict:
    try:
        payload = decode_refresh_token(refresh_token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token payload"
            )
        user_id = int(user_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired refresh token: {str(exc)}"
        )

    user = db.query(User).options(joinedload(User.employee)).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or deactivated"
        )

    new_access_token = create_access_token(data={"sub": str(user.id), "role": user.role})
    new_refresh_token = create_refresh_token(data={"sub": str(user.id), "role": user.role})

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "user": user
    }

def change_password(user_id: int, data: PasswordChange, db: Session) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password does not match"
        )

    try:
        user.hashed_password = hash_password(data.new_password)
        db.commit()
        return {"message": "Password changed successfully", "success": True}
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update password: {str(exc)}"
        )

def get_all_users(
    db: Session,
    page: int = 1,
    size: int = 20,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None
) -> PaginatedResponse[UserResponse]:
    query = db.query(User).options(joinedload(User.employee))

    if role:
        query = query.filter(User.role == role.upper())
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        query = query.filter((User.username.ilike(pattern)) | (User.email.ilike(pattern)))

    query = query.order_by(User.id.desc())
    return paginate(query, page, size)

def update_user_status(user_id: int, is_active: bool, db: Session, current_user: User) -> User:
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Only SUPER_ADMIN can alter status of ADMIN/SUPER_ADMIN
    if user.role in {"ADMIN", "SUPER_ADMIN"} and current_user.role != "SUPER_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Super Administrators can modify Admin accounts"
        )

    try:
        user.is_active = is_active
        db.commit()
        db.refresh(user)
        return user
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user status: {str(exc)}"
        )

def update_user_role(user_id: int, new_role: str, db: Session, current_user: User) -> User:
    if current_user.role != "SUPER_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Super Administrators can change user roles"
        )

    normalized = normalize_role(new_role)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        user.role = normalized
        db.commit()
        db.refresh(user)
        return user
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user role: {str(exc)}"
        )
