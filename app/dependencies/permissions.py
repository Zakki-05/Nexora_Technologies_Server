from typing import Annotated, Set
from fastapi import Depends, HTTPException, status
from app.models.user import User
from app.dependencies.auth import get_current_user

# Enterprise Hierarchical Role Matrix
SUPER_ADMIN_ROLES: Set[str] = {"PLATFORM_SUPER_ADMIN", "SUPER_ADMIN"}
ADMIN_ROLES: Set[str] = SUPER_ADMIN_ROLES | {"COMPANY_ADMIN", "ADMIN"}
HR_ROLES: Set[str] = ADMIN_ROLES | {"HR_MANAGER"}
FINANCE_ROLES: Set[str] = ADMIN_ROLES | {"FINANCE_MANAGER", "PAYROLL_MANAGER"}
AUDITOR_ROLES: Set[str] = ADMIN_ROLES | {"AUDITOR"}

def require_roles(*allowed_roles: str):
    allowed = {role.strip().upper() for role in allowed_roles}
    # Super admins always satisfy any role requirement
    allowed.update(SUPER_ADMIN_ROLES)

    def role_checker(
        current_user: Annotated[User, Depends(get_current_user)]
    ) -> User:
        user_role = current_user.role.strip().upper()
        if user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Insufficient privileges for role '{user_role}'"
            )
        return current_user

    return role_checker

def require_super_admin_only():
    def checker(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role.strip().upper() not in SUPER_ADMIN_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Super Admin privileges required"
            )
        return current_user
    return checker

# Ready-to-use Dependencies
get_current_admin = require_roles(*ADMIN_ROLES)
require_admin = get_current_admin
get_current_super_admin = require_super_admin_only()
require_super_admin = get_current_super_admin
require_hr = require_roles(*HR_ROLES)
require_finance = require_roles(*FINANCE_ROLES)
require_auditor = require_roles(*AUDITOR_ROLES)
get_current_employee = get_current_user
