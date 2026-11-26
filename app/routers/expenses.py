from typing import Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_admin
from app.models.user import User
from app.schemas.expense import (
    ExpenseClaimCreate,
    ExpenseClaimReview,
    ExpenseClaimResponse,
    ExpenseListResponse
)
from app.services.expense_service import ExpenseService

router = APIRouter()

@router.get("", response_model=ExpenseListResponse)
def get_all_expenses(
    status: Optional[str] = None,
    category: Optional[str] = None,
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all expense claims. Admins see all; employees see only their claims if not admin.
    """
    if current_user.role not in ["ADMIN", "SUPER_ADMIN"]:
        target_emp_id = current_user.employee.id if current_user.employee else -1
        return ExpenseService.get_all(db, status_filter=status, category_filter=category, employee_id=target_emp_id)

    return ExpenseService.get_all(db, status_filter=status, category_filter=category, employee_id=employee_id)

@router.get("/me", response_model=ExpenseListResponse)
def get_my_expenses(
    status: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get expense claims submitted by current employee.
    """
    emp_id = current_user.employee.id if current_user.employee else -1
    return ExpenseService.get_all(db, status_filter=status, category_filter=category, employee_id=emp_id)

@router.post("", response_model=ExpenseClaimResponse, status_code=status.HTTP_201_CREATED)
def submit_expense(
    data: ExpenseClaimCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Submit a new expense reimbursement claim.
    """
    return ExpenseService.create(db, data, current_user)

@router.patch("/{claim_id}/review", response_model=ExpenseClaimResponse)
def review_expense(
    claim_id: int,
    data: ExpenseClaimReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Approve or reject an expense claim (Admin/SuperAdmin only).
    """
    return ExpenseService.review(db, claim_id, data, current_user)

@router.delete("/{claim_id}")
def delete_expense(
    claim_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete an expense claim.
    """
    return ExpenseService.delete(db, claim_id, current_user)
