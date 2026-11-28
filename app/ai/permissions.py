from app.dependencies.permissions import (
    ADMIN_ROLES,
    AUDITOR_ROLES,
    FINANCE_ROLES,
    HR_ROLES,
    SUPER_ADMIN_ROLES,
)
from app.models.user import User


def get_role_name(user: User) -> str:
    return (user.role or "EMPLOYEE").strip().upper()


def is_super_admin(user: User) -> bool:
    return get_role_name(user) in SUPER_ADMIN_ROLES


def is_admin(user: User) -> bool:
    return get_role_name(user) in ADMIN_ROLES


def is_hr(user: User) -> bool:
    return get_role_name(user) in HR_ROLES


def is_finance(user: User) -> bool:
    return get_role_name(user) in FINANCE_ROLES


def is_auditor(user: User) -> bool:
    return get_role_name(user) in AUDITOR_ROLES


def get_ai_role_tier(user: User) -> str:
    role = get_role_name(user)
    if role in SUPER_ADMIN_ROLES:
        return "super_admin"
    if role in ADMIN_ROLES:
        return "admin"
    if role in HR_ROLES:
        return "hr"
    if role in FINANCE_ROLES:
        return "finance"
    if role in AUDITOR_ROLES:
        return "auditor"
    return "employee"
