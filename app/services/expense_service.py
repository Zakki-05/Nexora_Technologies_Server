from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from app.models.expense import ExpenseClaim
from app.models.employee import Employee
from app.models.user import User
from app.schemas.expense import ExpenseClaimCreate, ExpenseClaimReview, ExpenseClaimResponse, ExpenseListResponse

class ExpenseService:
    @staticmethod
    def _format_claim(claim: ExpenseClaim) -> ExpenseClaimResponse:
        emp = claim.employee
        dept_name = emp.department.name if emp and emp.department else "General"
        emp_name = emp.full_name if emp else "Unknown"
        emp_code = emp.employee_code if emp else "N/A"

        return ExpenseClaimResponse(
            id=claim.id,
            employee_id=claim.employee_id,
            employee_name=emp_name,
            employee_code=emp_code,
            department=dept_name,
            title=claim.title,
            category=claim.category,
            amount=float(claim.amount),
            approved_amount=float(claim.approved_amount) if claim.approved_amount is not None else None,
            expense_date=str(claim.expense_date),
            status=claim.status,
            notes=claim.notes,
            receipt_name=claim.receipt_name,
            reviewer_remarks=claim.reviewer_remarks,
            created_at=claim.created_at.isoformat() if claim.created_at else datetime.utcnow().isoformat()
        )

    @classmethod
    def get_all(
        cls,
        db: Session,
        status_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        employee_id: Optional[int] = None
    ) -> ExpenseListResponse:
        query = db.query(ExpenseClaim).options(
            joinedload(ExpenseClaim.employee).joinedload(Employee.department)
        )

        if status_filter:
            query = query.filter(ExpenseClaim.status == status_filter)
        if category_filter:
            query = query.filter(ExpenseClaim.category == category_filter)
        if employee_id:
            query = query.filter(ExpenseClaim.employee_id == employee_id)

        claims = query.order_by(ExpenseClaim.created_at.desc()).all()

        formatted = [cls._format_claim(c) for c in claims]
        total_amt = sum(c.amount for c in formatted)
        approved_amt = sum((c.approved_amount if c.approved_amount is not None else c.amount) for c in formatted if c.status == "APPROVED")
        pending_amt = sum(c.amount for c in formatted if c.status == "PENDING")

        return ExpenseListResponse(
            items=formatted,
            total=len(formatted),
            total_amount=round(total_amt, 2),
            approved_amount=round(approved_amt, 2),
            pending_amount=round(pending_amt, 2)
        )

    @classmethod
    def create(
        cls,
        db: Session,
        data: ExpenseClaimCreate,
        current_user: User
    ) -> ExpenseClaimResponse:
        if not current_user.employee:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User account does not have an associated employee profile."
            )

        claim = ExpenseClaim(
            employee_id=current_user.employee.id,
            title=data.title,
            category=data.category,
            amount=data.amount,
            expense_date=data.expense_date,
            notes=data.notes,
            receipt_name=data.receipt_name,
            status="PENDING"
        )
        db.add(claim)
        db.commit()
        db.refresh(claim)

        # Reload with relationships
        claim = db.query(ExpenseClaim).options(
            joinedload(ExpenseClaim.employee).joinedload(Employee.department)
        ).filter(ExpenseClaim.id == claim.id).first()

        return cls._format_claim(claim)

    @classmethod
    def review(
        cls,
        db: Session,
        claim_id: int,
        review_data: ExpenseClaimReview,
        reviewer: User
    ) -> ExpenseClaimResponse:
        claim = db.query(ExpenseClaim).options(
            joinedload(ExpenseClaim.employee).joinedload(Employee.department)
        ).filter(ExpenseClaim.id == claim_id).first()

        if not claim:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Expense claim with ID {claim_id} not found."
            )

        claim.status = review_data.status
        claim.reviewer_remarks = review_data.remarks
        claim.reviewed_by = reviewer.id
        claim.reviewed_at = datetime.utcnow()

        if review_data.status == "APPROVED":
            claim.approved_amount = review_data.approved_amount if review_data.approved_amount is not None else claim.amount
        else:
            claim.approved_amount = Decimal("0.00")

        db.commit()
        db.refresh(claim)
        return cls._format_claim(claim)

    @classmethod
    def delete(
        cls,
        db: Session,
        claim_id: int,
        current_user: User
    ) -> dict:
        claim = db.query(ExpenseClaim).filter(ExpenseClaim.id == claim_id).first()
        if not claim:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Expense claim with ID {claim_id} not found."
            )

        # Employees can only delete their own PENDING claims
        if current_user.role not in ["ADMIN", "SUPER_ADMIN"]:
            if not current_user.employee or claim.employee_id != current_user.employee.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to delete this expense claim."
                )
            if claim.status != "PENDING":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete an expense claim that has already been reviewed."
                )

        db.delete(claim)
        db.commit()
        return {"message": "Expense claim deleted successfully."}
