from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, List
import uuid

from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from app.models.leave import Leave
from app.models.employee import Employee
from app.models.user import User
from app.models.leave_balance import LeaveBalance
from app.models.leave_type import LeaveType
from app.models.leave_transaction import LeaveTransaction
from app.models.holiday import Holiday
from app.schemas.leave import (
    LeaveCreate,
    LeaveDecision,
    LeaveResponse,
    LeaveBalanceResponse,
    LeaveBalanceUpdate,
    LeaveTypeBalanceDetail,
    LeaveTypeCreate,
    LeaveTypeUpdate,
    LeaveTypeResponse,
    LeaveTransactionResponse,
    LeaveAdjustmentRequest
)
from app.schemas.common import PaginatedResponse
from app.utils.pagination import paginate

# ==================== HELPER & CALCULATION FUNCTIONS ====================

def calculate_leave_days(
    start_date: date,
    end_date: date,
    is_half_day: bool = False,
    exclude_weekends: bool = False,
    db: Optional[Session] = None
) -> float:
    """
    Calculates total leave days. Supports half-day (0.5), and optional
    exclusion of weekends (Saturday, Sunday) and corporate holidays.
    """
    if is_half_day:
        return 0.5

    # If simple calendar difference is requested (legacy compatibility)
    if not exclude_weekends and db is None:
        return float((end_date - start_date).days + 1)

    curr = start_date
    count = 0.0

    holiday_dates = set()
    if db is not None:
        holidays = db.query(Holiday.date).filter(
            Holiday.date >= start_date,
            Holiday.date <= end_date,
            Holiday.is_optional == False
        ).all()
        holiday_dates = {h[0] for h in holidays}

    while curr <= end_date:
        # Check weekend (Saturday = 5, Sunday = 6)
        if exclude_weekends and curr.weekday() in (5, 6):
            curr += timedelta(days=1)
            continue
        if curr in holiday_dates:
            curr += timedelta(days=1)
            continue
        count += 1.0
        curr += timedelta(days=1)

    return count

STANDARD_LEAVE_TYPES = [
    ("Annual Leave", "ANNUAL_LEAVE", "Paid vacation leave", 18, True, True, 10, 15, False, True),
    ("Sick Leave", "SICK_LEAVE", "Medical and health related absence", 12, True, False, 0, 7, True, True),
    ("Casual Leave", "CASUAL_LEAVE", "Unforeseen personal affairs", 10, True, False, 0, 3, False, True),
    ("Unpaid Leave", "UNPAID_LEAVE", "Leave without pay / Loss of Pay", 0, False, False, 0, 30, False, True),
    ("Maternity Leave", "MATERNITY_LEAVE", "Statutory maternity benefit", 180, True, False, 0, 180, True, False),
    ("Paternity Leave", "PATERNITY_LEAVE", "Parental leave for fathers", 15, True, False, 0, 15, False, False),
    ("Compensatory Off", "COMPENSATORY_OFF", "Credit for working on holidays/weekends", 0, True, True, 5, 2, False, True),
    ("Bereavement Leave", "BEREAVEMENT_LEAVE", "Leave for immediate family bereavement", 5, True, False, 0, 5, False, False),
    ("Marriage Leave", "MARRIAGE_LEAVE", "Special celebration leave for wedding", 5, True, False, 0, 5, False, False),
    ("Optional Holiday", "OPTIONAL_HOLIDAY", "Floating holiday from company list", 2, True, False, 0, 1, False, False),
]

def ensure_standard_leave_types(db: Session) -> None:
    """
    Ensures that standard corporate leave types are seeded if table is empty.
    """
    if db.query(LeaveType).count() == 0:
        for name, code, desc, alloc, is_paid, cf, max_cf, max_cons, req_doc, half_d in STANDARD_LEAVE_TYPES:
            lt = LeaveType(
                name=name,
                code=code,
                description=desc,
                annual_allocation=alloc,
                is_paid=is_paid,
                carry_forward_enabled=cf,
                max_carry_forward_days=max_cf,
                max_consecutive_days=max_cons,
                requires_document=req_doc,
                allow_half_day=half_d,
                is_active=True
            )
            db.add(lt)
        try:
            db.commit()
        except Exception:
            db.rollback()

def resolve_leave_type(
    db: Session,
    leave_type_id: Optional[int] = None,
    leave_type_str: Optional[str] = None
) -> LeaveType:
    """
    Resolves a LeaveType record by ID, code, or common names.
    Provides graceful fallbacks for legacy string types.
    """
    ensure_standard_leave_types(db)
    if leave_type_id:
        lt = db.query(LeaveType).filter(LeaveType.id == leave_type_id).first()
        if lt:
            return lt

    if leave_type_str:
        norm = leave_type_str.strip()
        # Direct code match
        lt = db.query(LeaveType).filter(LeaveType.code == norm.upper()).first()
        if lt:
            return lt

        # Name exact or ilike match
        lt = db.query(LeaveType).filter(LeaveType.name.ilike(norm)).first()
        if lt:
            return lt

        # Prefix mappings
        mappings = {
            "annual": "ANNUAL_LEAVE",
            "sick": "SICK_LEAVE",
            "casual": "CASUAL_LEAVE",
            "unpaid": "UNPAID_LEAVE",
            "maternity": "MATERNITY_LEAVE",
            "paternity": "PATERNITY_LEAVE",
            "compensatory": "COMPENSATORY_OFF",
            "comp": "COMPENSATORY_OFF",
            "bereavement": "BEREAVEMENT_LEAVE",
            "marriage": "MARRIAGE_LEAVE",
            "optional": "OPTIONAL_HOLIDAY"
        }
        for prefix, code in mappings.items():
            if norm.lower().startswith(prefix):
                lt = db.query(LeaveType).filter(LeaveType.code == code).first()
                if lt:
                    return lt

    # Default to first active leave type or fallback
    lt = db.query(LeaveType).filter(LeaveType.is_active == True).first()
    if not lt:
        # Seed basic if empty
        lt = LeaveType(
            name="Annual Leave",
            code="ANNUAL_LEAVE",
            description="Default Annual Leave",
            annual_allocation=15,
            is_paid=True,
            is_active=True
        )
        db.add(lt)
        db.commit()
        db.refresh(lt)
    return lt

def initialize_employee_leave_ledger(employee_id: int, db: Session) -> None:
    """
    Ensures that an employee has initial ALLOCATION transactions
    in the LeaveTransaction ledger for all active leave types.
    """
    ensure_standard_leave_types(db)
    current_year = datetime.now().year
    leave_types = db.query(LeaveType).filter(LeaveType.is_active == True).all()

    for lt in leave_types:
        if lt.annual_allocation > 0:
            ref_id = f"ALLOC-{employee_id}-{current_year}-{lt.code}"
            existing = db.query(LeaveTransaction).filter(
                LeaveTransaction.reference_id == ref_id
            ).first()
            if not existing:
                tx = LeaveTransaction(
                    employee_id=employee_id,
                    leave_type_id=lt.id,
                    transaction_type="ALLOCATION",
                    days=Decimal(str(lt.annual_allocation)),
                    reference_id=ref_id,
                    balance_after=Decimal(str(lt.annual_allocation)),
                    remarks=f"Annual allocation of {lt.annual_allocation} days for {current_year}",
                    created_by=None
                )
                db.add(tx)
    try:
        db.commit()
    except Exception:
        db.rollback()

def get_or_create_leave_balance(employee_id: int, db: Session) -> LeaveBalance:
    """
    Retrieves or initializes the legacy LeaveBalance record,
    and initializes ledger transactions.
    """
    balance = db.query(LeaveBalance).filter(
        LeaveBalance.employee_id == employee_id
    ).first()

    if not balance:
        balance = LeaveBalance(
            employee_id=employee_id,
            year=datetime.now().year,
            annual_total=18,
            annual_used=0,
            sick_total=12,
            sick_used=0,
            casual_total=10,
            casual_used=0,
            unpaid_used=0,
            pending_reserved=0,
            carried_forward=0
        )
        db.add(balance)
        db.commit()
        db.refresh(balance)

    initialize_employee_leave_ledger(employee_id, db)
    return balance

def get_leave_type_balance_metrics(
    employee_id: int,
    leave_type: LeaveType,
    db: Session
) -> LeaveTypeBalanceDetail:
    """
    Calculates detailed balance metrics for a specific leave type using the ledger:
    Available = Allocated + CarryForward + Adjustments - ApprovedConsumed - PendingReserved
    """
    transactions = db.query(LeaveTransaction).filter(
        LeaveTransaction.employee_id == employee_id,
        LeaveTransaction.leave_type_id == leave_type.id
    ).order_by(LeaveTransaction.id.asc()).all()

    allocated = Decimal("0.0")
    carried_forward = Decimal("0.0")
    manual_adjustments = Decimal("0.0")
    approved_consumed = Decimal("0.0")

    for tx in transactions:
        tx_type = tx.transaction_type.upper()
        days_val = Decimal(str(tx.days))
        if tx_type == "ALLOCATION":
            allocated += days_val
        elif tx_type == "CARRY_FORWARD":
            carried_forward += days_val
        elif tx_type == "MANUAL_ADJUSTMENT":
            manual_adjustments += days_val
        elif tx_type == "APPROVAL_DEDUCTION":
            approved_consumed += days_val
        elif tx_type == "CANCELLATION_REFUND":
            approved_consumed -= days_val
        elif tx_type == "EXPIRATION":
            allocated -= days_val

    # Fallback sync with legacy LeaveBalance if no transactions recorded yet
    balance = db.query(LeaveBalance).filter(LeaveBalance.employee_id == employee_id).first()
    if not transactions and balance:
        if leave_type.code in ["ANNUAL_LEAVE", "Annual"]:
            allocated = Decimal(str(balance.annual_total))
            approved_consumed = Decimal(str(balance.annual_used))
        elif leave_type.code in ["SICK_LEAVE", "Sick"]:
            allocated = Decimal(str(balance.sick_total))
            approved_consumed = Decimal(str(balance.sick_used))
        elif leave_type.code in ["CASUAL_LEAVE", "Casual"]:
            allocated = Decimal(str(balance.casual_total))
            approved_consumed = Decimal(str(balance.casual_used))

    # Calculate pending reserved days
    pending_leaves = db.query(Leave).filter(
        Leave.employee_id == employee_id,
        (Leave.leave_type_id == leave_type.id) |
        (Leave.leave_type == leave_type.name) |
        (Leave.leave_type == leave_type.code),
        Leave.status == "PENDING"
    ).all()
    pending_reserved = Decimal(str(sum(float(l.days_count) for l in pending_leaves)))

    settled_balance = allocated + carried_forward + manual_adjustments - approved_consumed

    if not leave_type.is_paid:
        available = Decimal("999.0")
    else:
        available = max(Decimal("0.0"), settled_balance - pending_reserved)

    return LeaveTypeBalanceDetail(
        leave_type_id=leave_type.id,
        leave_type_name=leave_type.name,
        leave_type_code=leave_type.code,
        annual_allocation=float(allocated),
        carried_forward=float(carried_forward),
        manual_adjustments=float(manual_adjustments),
        approved_consumed=float(approved_consumed),
        pending_reserved=float(pending_reserved),
        settled_balance=float(settled_balance),
        available=float(available),
        is_paid=leave_type.is_paid
    )

def format_balance_response(balance: LeaveBalance, db: Session) -> LeaveBalanceResponse:
    """
    Constructs LeaveBalanceResponse containing both legacy fields and detailed type balances.
    """
    ensure_standard_leave_types(db)
    leave_types = db.query(LeaveType).filter(LeaveType.is_active == True).all()
    type_details: List[LeaveTypeBalanceDetail] = []
    total_pending = Decimal("0.0")
    total_available = Decimal("0.0")

    for lt in leave_types:
        detail = get_leave_type_balance_metrics(balance.employee_id, lt, db)
        type_details.append(detail)
        total_pending += Decimal(str(detail.pending_reserved))
        if detail.is_paid:
            total_available += Decimal(str(detail.available))

    # Synchronize legacy columns
    annual_rem = max(0, balance.annual_total - balance.annual_used)
    sick_rem = max(0, balance.sick_total - balance.sick_used)
    casual_rem = max(0, balance.casual_total - balance.casual_used)

    return LeaveBalanceResponse(
        id=balance.id,
        employee_id=balance.employee_id,
        year=balance.year,
        annual_total=balance.annual_total,
        annual_used=balance.annual_used,
        annual_remaining=annual_rem,
        sick_total=balance.sick_total,
        sick_used=balance.sick_used,
        sick_remaining=sick_rem,
        casual_total=balance.casual_total,
        casual_used=balance.casual_used,
        casual_remaining=casual_rem,
        unpaid_used=balance.unpaid_used,
        pending_reserved=int(total_pending),
        carried_forward=balance.carried_forward,
        available_total=int(total_available),
        type_balances=type_details
    )

def check_overlapping_leaves(
    employee_id: int,
    start_date: date,
    end_date: date,
    db: Session,
    exclude_id: Optional[int] = None,
    is_half_day: bool = False,
    half_day_session: Optional[str] = None
) -> None:
    """
    Checks for overlapping pending or approved leave requests.
    Allows half-day leaves on the same day if one is FIRST_HALF and other is SECOND_HALF.
    """
    query = db.query(Leave).filter(
        Leave.employee_id == employee_id,
        Leave.status.in_(["PENDING", "APPROVED"]),
        Leave.start_date <= end_date,
        Leave.end_date >= start_date
    )
    if exclude_id:
        query = query.filter(Leave.id != exclude_id)

    overlaps = query.all()
    for overlap in overlaps:
        if is_half_day and overlap.is_half_day and start_date == end_date == overlap.start_date == overlap.end_date:
            if half_day_session and overlap.half_day_session and half_day_session != overlap.half_day_session:
                continue
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have a {overlap.status.lower()} leave request overlapping with this period ({overlap.start_date} to {overlap.end_date})"
        )

# ==================== CORE LEAVE WORKFLOW ====================

def apply_leave(employee_id: int, data: LeaveCreate, db: Session) -> Leave:
    """
    Submits a leave application:
    1. Validates employee existence.
    2. Resolves corporate LeaveType and policy rules.
    3. Excludes weekends and holidays when configured.
    4. Enforces balance availability, reserving pending days.
    5. Rejects overlapping applications.
    """
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    leave_type = resolve_leave_type(db, data.leave_type_id, data.leave_type)

    if data.is_half_day and not leave_type.allow_half_day:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Half-day leaves are not permitted for {leave_type.name}"
        )

    check_overlapping_leaves(
        employee_id=employee_id,
        start_date=data.start_date,
        end_date=data.end_date,
        db=db,
        is_half_day=data.is_half_day,
        half_day_session=data.half_day_session
    )

    days_count = calculate_leave_days(
        start_date=data.start_date,
        end_date=data.end_date,
        is_half_day=data.is_half_day,
        exclude_weekends=bool(data.exclude_weekends),
        db=db if data.exclude_weekends else None
    )

    if days_count <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requested date range contains no working days (all weekends or company holidays)"
        )

    if leave_type.max_consecutive_days and days_count > leave_type.max_consecutive_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Requested duration ({days_count} days) exceeds maximum consecutive limit ({leave_type.max_consecutive_days} days) for {leave_type.name}"
        )

    balance = get_or_create_leave_balance(employee_id, db)

    # Balance validation
    if leave_type.is_paid:
        metrics = get_leave_type_balance_metrics(employee_id, leave_type, db)
        available = metrics.available

        # Also respect legacy fields if updated directly in tests
        norm_type = data.leave_type.lower()
        if "annual" in norm_type:
            legacy_rem = balance.annual_total - balance.annual_used
            available = min(available, float(legacy_rem))
        elif "sick" in norm_type:
            legacy_rem = balance.sick_total - balance.sick_used
            available = min(available, float(legacy_rem))
        elif "casual" in norm_type:
            legacy_rem = balance.casual_total - balance.casual_used
            available = min(available, float(legacy_rem))

        if days_count > available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient {data.leave_type.lower()} leave balance. Requested: {days_count}, Remaining: {available}"
            )

    try:
        leave = Leave(
            employee_id=employee_id,
            leave_type_id=leave_type.id,
            leave_type=data.leave_type,
            start_date=data.start_date,
            end_date=data.end_date,
            days_count=days_count,
            is_half_day=data.is_half_day,
            half_day_session=data.half_day_session if data.is_half_day else None,
            reason=data.reason,
            status="PENDING",
            approved_by=None
        )
        db.add(leave)
        balance.pending_reserved = int(balance.pending_reserved + days_count)
        db.commit()
        db.refresh(leave)
        return leave
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit leave request: {str(exc)}"
        )

def review_leave(
    leave_id: int,
    data: LeaveDecision,
    admin_user_id: int,
    db: Session
) -> Leave:
    """
    Processes administrative review (APPROVED / REJECTED):
    1. Prevents self-approval.
    2. On APPROVAL: Creates append-only APPROVAL_DEDUCTION in LeaveTransaction.
    3. On REJECTION: Releases pending reservation; leaves balance intact.
    4. Enforces idempotency and prevents double-processing.
    """
    leave = db.query(Leave).filter(Leave.id == leave_id).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")

    if leave.status.upper() != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Leave request has already been processed (Current status: {leave.status})"
        )

    # Self-approval restriction
    admin_emp = db.query(Employee).filter(Employee.user_id == admin_user_id).first()
    if admin_emp and admin_emp.id == leave.employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employees cannot approve their own leave requests"
        )

    decision_status = data.status.upper()
    leave_type = resolve_leave_type(db, leave.leave_type_id, leave.leave_type)
    balance = get_or_create_leave_balance(leave.employee_id, db)

    try:
        leave.status = decision_status
        leave.approved_by = admin_user_id

        if decision_status == "REJECTED":
            leave.rejection_reason = data.rejection_reason
            # Release pending reservation without deduction
            balance.pending_reserved = max(0, int(balance.pending_reserved - leave.days_count))

        elif decision_status == "APPROVED":
            metrics = get_leave_type_balance_metrics(leave.employee_id, leave_type, db)
            days_dec = Decimal(str(leave.days_count))

            # Verify balance is still sufficient
            if leave_type.is_paid and Decimal(str(metrics.settled_balance)) < days_dec:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Insufficient settled leave balance to approve this request"
                )

            # Record immutable financial-style ledger deduction
            ref_id = f"APPR-LEAVE-{leave.id}"
            existing_tx = db.query(LeaveTransaction).filter(
                LeaveTransaction.reference_id == ref_id
            ).first()

            new_balance_after = Decimal(str(metrics.settled_balance)) - days_dec
            if not existing_tx:
                tx = LeaveTransaction(
                    employee_id=leave.employee_id,
                    leave_type_id=leave_type.id,
                    transaction_type="APPROVAL_DEDUCTION",
                    days=days_dec,
                    reference_id=ref_id,
                    balance_after=new_balance_after,
                    remarks=f"Approved leave #{leave.id} ({leave.start_date} to {leave.end_date})",
                    created_by=admin_user_id
                )
                db.add(tx)

            # Update legacy balance
            balance.pending_reserved = max(0, int(balance.pending_reserved - leave.days_count))
            norm_type = leave.leave_type.lower()
            if "annual" in norm_type:
                balance.annual_used += int(leave.days_count)
            elif "sick" in norm_type:
                balance.sick_used += int(leave.days_count)
            elif "casual" in norm_type:
                balance.casual_used += int(leave.days_count)
            elif "unpaid" in norm_type:
                balance.unpaid_used += int(leave.days_count)

        db.commit()
        db.refresh(leave)
        return leave
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process leave review: {str(exc)}"
        )

def cancel_leave(
    leave_id: int,
    user_or_emp_id: int,
    db: Session
) -> Leave:
    """
    Cancels a leave request:
    - If PENDING: marks CANCELLED and releases pending reservation.
    - If APPROVED: restores consumed quota via CANCELLATION_REFUND transaction.
    """
    leave = db.query(Leave).filter(Leave.id == leave_id).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")

    if leave.status.upper() == "CANCELLED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Leave request is already cancelled"
        )

    if leave.status.upper() not in ["PENDING", "APPROVED"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel leave request with status {leave.status}"
        )

    leave_type = resolve_leave_type(db, leave.leave_type_id, leave.leave_type)
    balance = get_or_create_leave_balance(leave.employee_id, db)
    was_approved = (leave.status.upper() == "APPROVED")

    try:
        leave.status = "CANCELLED"

        if not was_approved:
            # Release pending reservation
            balance.pending_reserved = max(0, int(balance.pending_reserved - leave.days_count))
        else:
            # Restore previously consumed quota via CANCELLATION_REFUND
            ref_id = f"CANC-LEAVE-{leave.id}"
            existing_refund = db.query(LeaveTransaction).filter(
                LeaveTransaction.reference_id == ref_id
            ).first()

            metrics = get_leave_type_balance_metrics(leave.employee_id, leave_type, db)
            days_dec = Decimal(str(leave.days_count))
            new_balance_after = Decimal(str(metrics.settled_balance)) + days_dec

            if not existing_refund:
                tx = LeaveTransaction(
                    employee_id=leave.employee_id,
                    leave_type_id=leave_type.id,
                    transaction_type="CANCELLATION_REFUND",
                    days=days_dec,
                    reference_id=ref_id,
                    balance_after=new_balance_after,
                    remarks=f"Cancelled approved leave #{leave.id}. Restored {leave.days_count} days.",
                    created_by=None
                )
                db.add(tx)

            # Update legacy counters
            norm_type = leave.leave_type.lower()
            if "annual" in norm_type:
                balance.annual_used = max(0, int(balance.annual_used - leave.days_count))
            elif "sick" in norm_type:
                balance.sick_used = max(0, int(balance.sick_used - leave.days_count))
            elif "casual" in norm_type:
                balance.casual_used = max(0, int(balance.casual_used - leave.days_count))
            elif "unpaid" in norm_type:
                balance.unpaid_used = max(0, int(balance.unpaid_used - leave.days_count))

        db.commit()
        db.refresh(leave)
        return leave
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel leave request: {str(exc)}"
        )

def adjust_leave_balance(
    data: LeaveAdjustmentRequest,
    admin_user_id: int,
    db: Session
) -> LeaveTransactionResponse:
    """
    Administrative manual balance adjustment (adds/subtracts days)
    with a mandatory audit record in LeaveTransaction.
    """
    employee = db.query(Employee).filter(Employee.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    leave_type = db.query(LeaveType).filter(LeaveType.id == data.leave_type_id).first()
    if not leave_type:
        raise HTTPException(status_code=404, detail="Leave type not found")

    metrics = get_leave_type_balance_metrics(data.employee_id, leave_type, db)
    adj_days = Decimal(str(data.adjustment_days))
    new_balance = Decimal(str(metrics.settled_balance)) + adj_days

    ref_id = f"ADJ-{data.employee_id}-{uuid.uuid4().hex[:8]}"

    try:
        tx = LeaveTransaction(
            employee_id=data.employee_id,
            leave_type_id=data.leave_type_id,
            transaction_type="MANUAL_ADJUSTMENT",
            days=adj_days,
            reference_id=ref_id,
            balance_after=new_balance,
            remarks=data.remarks,
            created_by=admin_user_id
        )
        db.add(tx)

        # Sync legacy balance if applicable
        balance = get_or_create_leave_balance(data.employee_id, db)
        if "annual" in leave_type.code.lower():
            balance.annual_total = max(0, int(balance.annual_total + adj_days))
        elif "sick" in leave_type.code.lower():
            balance.sick_total = max(0, int(balance.sick_total + adj_days))
        elif "casual" in leave_type.code.lower():
            balance.casual_total = max(0, int(balance.casual_total + adj_days))

        db.commit()
        db.refresh(tx)

        return LeaveTransactionResponse(
            id=tx.id,
            employee_id=tx.employee_id,
            leave_type_id=tx.leave_type_id,
            leave_type_name=leave_type.name,
            leave_type_code=leave_type.code,
            transaction_type=tx.transaction_type,
            days=float(tx.days),
            reference_id=tx.reference_id,
            balance_after=float(tx.balance_after),
            remarks=tx.remarks,
            created_by=tx.created_by,
            created_at=tx.created_at
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to adjust leave balance: {str(exc)}"
        )

def get_leave_ledger(
    employee_id: int,
    db: Session,
    page: int = 1,
    size: int = 20,
    leave_type_id: Optional[int] = None
) -> PaginatedResponse[LeaveTransactionResponse]:
    """
    Returns the append-only audit ledger of leave transactions for an employee.
    """
    query = db.query(LeaveTransaction).filter(
        LeaveTransaction.employee_id == employee_id
    )
    if leave_type_id:
        query = query.filter(LeaveTransaction.leave_type_id == leave_type_id)

    query = query.order_by(LeaveTransaction.id.desc())
    paginated = paginate(query, page, size)

    # Attach leave type details
    items: List[LeaveTransactionResponse] = []
    lt_cache = {}
    for tx in paginated.items:
        if tx.leave_type_id not in lt_cache:
            lt_cache[tx.leave_type_id] = db.query(LeaveType).filter(LeaveType.id == tx.leave_type_id).first()
        lt = lt_cache[tx.leave_type_id]

        items.append(LeaveTransactionResponse(
            id=tx.id,
            employee_id=tx.employee_id,
            leave_type_id=tx.leave_type_id,
            leave_type_name=lt.name if lt else None,
            leave_type_code=lt.code if lt else None,
            transaction_type=tx.transaction_type,
            days=float(tx.days),
            reference_id=tx.reference_id,
            balance_after=float(tx.balance_after),
            remarks=tx.remarks,
            created_by=tx.created_by,
            created_at=tx.created_at
        ))

    return PaginatedResponse[LeaveTransactionResponse](
        items=items,
        total=paginated.total,
        page=paginated.page,
        size=paginated.size,
        pages=paginated.pages
    )

# ==================== QUERY & MANAGEMENT APIS ====================

def get_employee_leaves(
    employee_id: int,
    db: Session,
    page: int = 1,
    size: int = 20,
    status_filter: Optional[str] = None
) -> PaginatedResponse[LeaveResponse]:
    query = db.query(Leave).options(
        joinedload(Leave.approver)
    ).filter(Leave.employee_id == employee_id)

    if status_filter:
        query = query.filter(Leave.status == status_filter.upper())

    query = query.order_by(Leave.id.desc())
    return paginate(query, page, size)

def get_all_leaves(
    db: Session,
    page: int = 1,
    size: int = 20,
    status_filter: Optional[str] = None,
    department_id: Optional[int] = None,
    employee_id: Optional[int] = None
) -> PaginatedResponse[LeaveResponse]:
    query = db.query(Leave).options(
        joinedload(Leave.employee),
        joinedload(Leave.approver)
    )

    if status_filter:
        query = query.filter(Leave.status == status_filter.upper())
    if employee_id:
        query = query.filter(Leave.employee_id == employee_id)
    if department_id:
        query = query.join(Employee, Employee.id == Leave.employee_id).filter(
            Employee.department_id == department_id
        )

    query = query.order_by(Leave.id.desc())
    return paginate(query, page, size)

def get_employee_balance(employee_id: int, db: Session) -> LeaveBalanceResponse:
    balance = get_or_create_leave_balance(employee_id, db)
    return format_balance_response(balance, db)

def update_employee_balance(
    employee_id: int,
    data: LeaveBalanceUpdate,
    db: Session
) -> LeaveBalanceResponse:
    balance = get_or_create_leave_balance(employee_id, db)

    try:
        if data.annual_total is not None:
            balance.annual_total = data.annual_total
        if data.sick_total is not None:
            balance.sick_total = data.sick_total
        if data.casual_total is not None:
            balance.casual_total = data.casual_total

        db.commit()
        db.refresh(balance)
        return format_balance_response(balance, db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update leave balance: {str(exc)}"
        )

def delete_leave(leave_id: int, db: Session) -> dict:
    leave = db.query(Leave).filter(Leave.id == leave_id).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")

    if leave.status.upper() != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending leave requests can be deleted"
        )

    balance = get_or_create_leave_balance(leave.employee_id, db)
    try:
        balance.pending_reserved = max(0, int(balance.pending_reserved - leave.days_count))
        db.delete(leave)
        db.commit()
        return {"message": "Leave request deleted successfully", "success": True}
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete leave: {str(exc)}"
        )

# ==================== LEAVE TYPE CRUD ====================

def get_all_leave_types(db: Session, active_only: bool = True) -> List[LeaveType]:
    ensure_standard_leave_types(db)
    query = db.query(LeaveType)
    if active_only:
        query = query.filter(LeaveType.is_active == True)
    return query.order_by(LeaveType.id.asc()).all()

def get_leave_type_by_id(leave_type_id: int, db: Session) -> LeaveType:
    lt = db.query(LeaveType).filter(LeaveType.id == leave_type_id).first()
    if not lt:
        raise HTTPException(status_code=404, detail="Leave type not found")
    return lt

def create_leave_type(data: LeaveTypeCreate, db: Session) -> LeaveType:
    existing = db.query(LeaveType).filter(
        (LeaveType.code == data.code.upper()) | (LeaveType.name == data.name)
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Leave type with code '{data.code}' or name '{data.name}' already exists"
        )

    try:
        lt = LeaveType(
            name=data.name,
            code=data.code.upper(),
            description=data.description,
            annual_allocation=data.annual_allocation,
            is_paid=data.is_paid,
            carry_forward_enabled=data.carry_forward_enabled,
            max_carry_forward_days=data.max_carry_forward_days,
            max_consecutive_days=data.max_consecutive_days,
            requires_document=data.requires_document,
            allow_half_day=data.allow_half_day,
            is_active=data.is_active
        )
        db.add(lt)
        db.commit()
        db.refresh(lt)
        return lt
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create leave type: {str(exc)}"
        )

def update_leave_type(leave_type_id: int, data: LeaveTypeUpdate, db: Session) -> LeaveType:
    lt = get_leave_type_by_id(leave_type_id, db)

    try:
        update_dict = data.model_dump(exclude_unset=True)
        if "code" in update_dict and update_dict["code"]:
            update_dict["code"] = update_dict["code"].upper()
        for key, value in update_dict.items():
            setattr(lt, key, value)

        db.commit()
        db.refresh(lt)
        return lt
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update leave type: {str(exc)}"
        )

def delete_leave_type(leave_type_id: int, db: Session) -> dict:
    lt = get_leave_type_by_id(leave_type_id, db)

    # Check if used in leaves or transactions
    leaves_count = db.query(Leave).filter(Leave.leave_type_id == leave_type_id).count()
    tx_count = db.query(LeaveTransaction).filter(LeaveTransaction.leave_type_id == leave_type_id).count()

    if leaves_count > 0 or tx_count > 0:
        # Soft delete / deactivate to maintain referential integrity
        lt.is_active = False
        db.commit()
        return {"message": f"Leave type '{lt.name}' has existing records; it has been deactivated.", "success": True}

    try:
        db.delete(lt)
        db.commit()
        return {"message": f"Leave type '{lt.name}' deleted successfully", "success": True}
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete leave type: {str(exc)}"
        )
