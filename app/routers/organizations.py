from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.organization import Organization
from app.models.employee import Employee
from app.models.user import User
from app.schemas.organization import OrganizationResponse
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_admin

router = APIRouter()

SUBSCRIPTION_PLANS: List[Dict[str, Any]] = [
    {
        "plan_code": "FREE",
        "name": "Community Free",
        "price_inr": 0,
        "billing_period": "forever",
        "max_employees": 15,
        "features": [
            "Up to 15 Active Employees",
            "Single Session Attendance Punch",
            "Standard Leave Management",
            "Community Support"
        ]
    },
    {
        "plan_code": "STARTER",
        "name": "Growth Starter",
        "price_inr": 2999,
        "billing_period": "month",
        "max_employees": 50,
        "features": [
            "Up to 50 Active Employees",
            "Multi-Session Attendance & Breaks",
            "Indian Statutory Payroll Slips",
            "Document Storage (10 GB)",
            "Email Broadcast Notifications"
        ]
    },
    {
        "plan_code": "PROFESSIONAL",
        "name": "Business Pro",
        "price_inr": 7999,
        "billing_period": "month",
        "max_employees": 250,
        "features": [
            "Up to 250 Active Employees",
            "Interactive Organization Hierarchy Chart",
            "Corporate Expense Claims & Approvals",
            "Granular RBAC (HR, Finance, Auditor)",
            "Audit Trail Logging & 1-Click Excel Exports"
        ]
    },
    {
        "plan_code": "ENTERPRISE",
        "name": "Enterprise Unlimited",
        "price_inr": 19999,
        "billing_period": "month",
        "max_employees": 10000,
        "features": [
            "Unlimited Employees & Departments",
            "24/7 Nexora AI Copilot with Statutory Law Engine",
            "Multi-Tenant Isolation Scoping",
            "Progressive Web Application (PWA) & Native Mobile Wrapper",
            "99.9% Uptime SLA & Priority Engineering Support"
        ]
    }
]

@router.get("/subscription/plans")
def get_subscription_plans():
    """
    Get all available commercial SaaS subscription tiers.
    """
    return {
        "currency": "INR",
        "plans": SUBSCRIPTION_PLANS
    }

@router.get("/current/subscription")
def get_current_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get active subscription usage and plan quota for the current organization.
    """
    org_id = getattr(current_user, "organization_id", 1) or 1
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        org = db.query(Organization).first()

    total_employees = db.query(Employee).filter(Employee.organization_id == (org.id if org else 1)).count()

    plan_info = next(
        (p for p in SUBSCRIPTION_PLANS if p["plan_code"] == (org.subscription_plan if org else "ENTERPRISE")),
        SUBSCRIPTION_PLANS[-1]
    )

    return {
        "organization_id": org.id if org else 1,
        "organization_name": org.name if org else "Nexora Technologies Inc.",
        "subscription_plan": org.subscription_plan if org else "ENTERPRISE",
        "plan_details": plan_info,
        "usage": {
            "current_employees": total_employees,
            "max_employees": plan_info["max_employees"],
            "utilization_percent": round((total_employees / plan_info["max_employees"] * 100), 1) if plan_info["max_employees"] > 0 else 0
        },
        "status": "ACTIVE"
    }

@router.get("/current", response_model=OrganizationResponse)
def get_current_organization(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get organization details for current user's tenant.
    """
    org_id = getattr(current_user, "organization_id", 1) or 1
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        org = db.query(Organization).first()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization tenant not configured."
        )
    return org

@router.get("", response_model=List[OrganizationResponse])
def get_all_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    List all organizations (SuperAdmin/Admin only).
    """
    return db.query(Organization).filter(Organization.is_active == True).all()
