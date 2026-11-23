from typing import Annotated
from fastapi import Depends, HTTPException, status
from app.models.user import User
from app.dependencies.auth import get_current_user

def require_roles(*allowed_roles: str):
    allowed = {role.strip().upper() for role in allowed_roles}
    # SUPER_ADMIN inherently inherits all administrative permissions
    allowed.add("SUPER_ADMIN")

    def role_checker(
        current_user: Annotated[User, Depends(get_current_user)]
    ) -> User:
        user_role = current_user.role.strip().upper()
        if user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Requires one of {list(allowed)} roles"
            )
        return current_user

    return role_checker

def require_super_admin_only():
    def checker(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role.strip().upper() != "SUPER_ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Super Admin privileges required"
            )
        return current_user
    return checker

get_current_admin = require_roles("ADMIN", "SUPER_ADMIN")
get_current_super_admin = require_super_admin_only()
get_current_employee = get_current_user
