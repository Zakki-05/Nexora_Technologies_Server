from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import OrganizationResponse
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_admin

router = APIRouter()

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
