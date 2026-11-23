import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status, UploadFile
from app.models.employee import Employee
from app.models.department import Department
from app.models.user import User
from app.models.leave_balance import LeaveBalance
from app.models.notification import Notification
from app.schemas.employee import (
    EmployeeCreate,
    EmployeePatch,
    EmployeeUpdate,
    EmployeeSelfUpdate,
    EmployeeResponse,
    AvatarPendingRequestResponse
)
from app.schemas.common import PaginatedResponse
from app.utils.pagination import paginate
from app.services.audit_service import log_audit

def generate_employee_code(db: Session) -> str:
    count = db.query(Employee).count()
    candidate = f"EMP-{1001 + count}"
    while db.query(Employee).filter(Employee.employee_code == candidate).first():
        count += 1
        candidate = f"EMP-{1001 + count}"
    return candidate

def ensure_employee_profile(user: User, db: Session) -> Employee:
    """
    Guarantees an Employee profile exists for the given User account.
    If none exists, auto-provisions one with default department and leave balance.
    """
    if getattr(user, "employee", None):
        return user.employee

    employee = db.query(Employee).options(
        joinedload(Employee.department),
        joinedload(Employee.user),
        joinedload(Employee.leave_balance)
    ).filter(Employee.user_id == user.id).first()

    if employee:
        return employee

    # Department: Pick first existing department or create a default
    dept = db.query(Department).first()
    if not dept:
        dept = Department(name="Operations", description="Operations & Administration")
        db.add(dept)
        db.commit()
        db.refresh(dept)

    code = generate_employee_code(db)

    if user.username:
        clean_name = user.username.replace("_", " ").replace(".", " ").title()
    else:
        clean_name = (user.email.split("@")[0] if user.email else "User").replace("_", " ").replace(".", " ").title()

    unique_phone = f"+9198{str(user.id).zfill(8)}"
    existing_phone = db.query(Employee).filter(Employee.phone == unique_phone).first()
    if existing_phone:
        import random
        unique_phone = f"+91{random.randint(6000000000, 9999999999)}"

    role_str = (user.role or "EMPLOYEE").upper()
    if role_str == "SUPER_ADMIN":
        pos = "Chief Technology Officer"
    elif role_str == "ADMIN":
        pos = "Operations Director"
    else:
        pos = "Staff Member"

    new_emp = Employee(
        user_id=user.id,
        department_id=dept.id,
        employee_code=code,
        full_name=clean_name,
        phone=unique_phone,
        hire_date=date.today(),
        position=pos,
        salary=Decimal("60000.00"),
        gender="Male",
        employment_status="ACTIVE"
    )
    db.add(new_emp)
    db.commit()
    db.refresh(new_emp)

    # Initialize leave balance
    bal = db.query(LeaveBalance).filter(LeaveBalance.employee_id == new_emp.id).first()
    if not bal:
        bal = LeaveBalance(
            employee_id=new_emp.id,
            annual_total=18,
            annual_used=0,
            sick_total=12,
            sick_used=0,
            casual_total=12,
            casual_used=0,
            unpaid_used=0,
            pending_reserved=0,
            carried_forward=0
        )
        db.add(bal)
        db.commit()

    # Initialize default salary structure
    from app.models.salary_structure import SalaryStructure
    struct = db.query(SalaryStructure).filter(SalaryStructure.employee_id == new_emp.id).first()
    if not struct:
        base = new_emp.salary
        struct = SalaryStructure(
            employee_id=new_emp.id,
            basic_salary=Decimal(str(round(float(base) * 0.50, 2))),
            hra=Decimal(str(round(float(base) * 0.25, 2))),
            da=Decimal(str(round(float(base) * 0.10, 2))),
            conveyance=Decimal("2000.00"),
            medical_allowance=Decimal("1500.00"),
            special_allowance=Decimal(str(max(0.0, round(float(base) * 0.15 - 3500.0, 2)))),
            pf_deduction_rate=Decimal("12.00"),
            professional_tax=Decimal("200.00"),
            esi_rate=Decimal("0.75"),
            tds_rate=Decimal("0.00"),
            is_active=True
        )
        db.add(struct)
        db.commit()

    return new_emp

def get_all_employees(
    db: Session,
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    department_id: Optional[int] = None,
    employment_status: Optional[str] = None
) -> PaginatedResponse[EmployeeResponse]:
    query = db.query(Employee).options(
        joinedload(Employee.department),
        joinedload(Employee.user),
        joinedload(Employee.leave_balance)
    )

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            (Employee.full_name.ilike(pattern)) |
            (Employee.phone.ilike(pattern)) |
            (Employee.employee_code.ilike(pattern)) |
            (Employee.position.ilike(pattern))
        )

    if department_id:
        query = query.filter(Employee.department_id == department_id)

    if employment_status:
        query = query.filter(Employee.employment_status == employment_status.upper())

    query = query.order_by(Employee.id.desc())
    return paginate(query, page, size)

def get_employee_by_id(employee_id: int, db: Session) -> Employee:
    employee = db.query(Employee).options(
        joinedload(Employee.department),
        joinedload(Employee.user),
        joinedload(Employee.leave_balance)
    ).filter(Employee.id == employee_id).first()

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found"
        )
    return employee

def get_employee_by_user_id(user_id: int, db: Session) -> Employee:
    employee = db.query(Employee).options(
        joinedload(Employee.department),
        joinedload(Employee.user),
        joinedload(Employee.leave_balance)
    ).filter(Employee.user_id == user_id).first()

    if not employee:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return ensure_employee_profile(user, db)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee profile not found for this user account"
        )
    return employee

def create_employee(data: EmployeeCreate, db: Session) -> Employee:
    user = None
    if data.user_id:
        user = db.query(User).filter(User.id == data.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User account not found")
        if user.employee:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This user account already has an employee profile"
            )
    else:
        # Auto-provision user account from email and password
        emp_email = (data.email or "").strip().lower()
        if not emp_email:
            # Generate corporate email if neither user_id nor email passed
            clean_first = data.full_name.strip().split()[0].lower()
            emp_email = f"{clean_first}.{data.phone[-4:]}@nexora.tech"

        existing_user = db.query(User).filter(User.email.ilike(emp_email)).first()
        if existing_user:
            if existing_user.employee:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A user with email '{emp_email}' already has an employee profile"
                )
            user = existing_user
        else:
            from app.utils.security import hash_password
            raw_password = (data.password or "Employee@123").strip()
            uname = (data.username or emp_email.split("@")[0]).strip()
            # Ensure unique username
            base_uname = uname
            c = 1
            while db.query(User).filter(User.username == uname).first():
                uname = f"{base_uname}_{c}"
                c += 1

            user = User(
                username=uname,
                email=emp_email,
                hashed_password=hash_password(raw_password),
                role="EMPLOYEE",
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    department = db.query(Department).filter(Department.id == data.department_id).first()
    if not department:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found"
        )

    existing_phone = db.query(Employee).filter(Employee.phone == data.phone).first()
    if existing_phone:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This phone number is already registered"
        )

    code = data.employee_code or generate_employee_code(db)
    if data.employee_code:
        existing_code = db.query(Employee).filter(Employee.employee_code == data.employee_code).first()
        if existing_code:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Employee code '{data.employee_code}' already exists"
            )

    emp_dict = data.model_dump()
    emp_dict.pop("email", None)
    emp_dict.pop("password", None)
    emp_dict.pop("username", None)
    emp_dict["user_id"] = user.id
    emp_dict["employee_code"] = code

    try:
        employee = Employee(**emp_dict)
        db.add(employee)
        db.commit()
        db.refresh(employee)

        # Initialize default leave balance for new employee
        balance = LeaveBalance(
            employee_id=employee.id,
            annual_total=18,
            annual_used=0,
            sick_total=12,
            sick_used=0,
            casual_total=12,
            casual_used=0,
            unpaid_used=0
        )
        db.add(balance)
        db.commit()

        # Initialize default salary structure
        from app.models.salary_structure import SalaryStructure
        struct = db.query(SalaryStructure).filter(SalaryStructure.employee_id == employee.id).first()
        if not struct:
            base = employee.salary
            struct = SalaryStructure(
                employee_id=employee.id,
                basic_salary=Decimal(str(round(float(base) * 0.50, 2))),
                hra=Decimal(str(round(float(base) * 0.25, 2))),
                da=Decimal(str(round(float(base) * 0.10, 2))),
                conveyance=Decimal("2000.00"),
                medical_allowance=Decimal("1500.00"),
                special_allowance=Decimal(str(max(0.0, round(float(base) * 0.15 - 3500.0, 2)))),
                pf_deduction_rate=Decimal("12.00"),
                professional_tax=Decimal("200.00"),
                esi_rate=Decimal("0.75"),
                tds_rate=Decimal("0.00"),
                is_active=True
            )
            db.add(struct)
            db.commit()

        db.refresh(employee)
        return employee
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create employee: {str(exc)}"
        )

def update_employee(employee_id: int, data: EmployeeUpdate, db: Session) -> Employee:
    employee = get_employee_by_id(employee_id, db)

    department = db.query(Department).filter(Department.id == data.department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")

    existing_phone = db.query(Employee).filter(
        Employee.phone == data.phone,
        Employee.id != employee_id
    ).first()
    if existing_phone:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This phone number is already in use by another employee"
        )

    try:
        for key, value in data.model_dump().items():
            setattr(employee, key, value)
        db.commit()
        db.refresh(employee)
        return employee
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update employee: {str(exc)}"
        )

def patch_employee(employee_id: int, data: EmployeePatch, db: Session) -> Employee:
    employee = get_employee_by_id(employee_id, db)
    update_data = data.model_dump(exclude_unset=True)

    if "department_id" in update_data and update_data["department_id"] is not None:
        department = db.query(Department).filter(Department.id == update_data["department_id"]).first()
        if not department:
            raise HTTPException(status_code=404, detail="Department not found")

    if "phone" in update_data and update_data["phone"] is not None:
        existing_phone = db.query(Employee).filter(
            Employee.phone == update_data["phone"],
            Employee.id != employee_id
        ).first()
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This phone number is already in use by another employee"
            )

    try:
        for key, value in update_data.items():
            setattr(employee, key, value)
        db.commit()
        db.refresh(employee)
        return employee
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to patch employee: {str(exc)}"
        )

def update_employee_status(employee_id: int, status_value: str, db: Session) -> Employee:
    valid_statuses = {"ACTIVE", "INACTIVE", "TERMINATED", "ON_LEAVE"}
    normalized = status_value.strip().upper()
    if normalized not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid employment status. Allowed: {list(valid_statuses)}"
        )

    employee = get_employee_by_id(employee_id, db)
    try:
        employee.employment_status = normalized
        if employee.user:
            employee.user.is_active = (normalized == "ACTIVE")
        db.commit()
        db.refresh(employee)
        return employee
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update employee status: {str(exc)}"
        )

def update_my_profile(user_id: int, data: EmployeeSelfUpdate, db: Session) -> Employee:
    employee = get_employee_by_user_id(user_id, db)
    update_data = data.model_dump(exclude_unset=True)

    if "phone" in update_data and update_data["phone"] is not None:
        existing = db.query(Employee).filter(
            Employee.phone == update_data["phone"],
            Employee.id != employee.id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Phone number already registered to another employee"
            )

    try:
        for key, value in update_data.items():
            setattr(employee, key, value)
        db.commit()
        db.refresh(employee)
        return employee
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(exc)}"
        )

def delete_employee(employee_id: int, db: Session, hard_delete: bool = False) -> dict:
    employee = get_employee_by_id(employee_id, db)

    try:
        if hard_delete:
            db.delete(employee)
            db.commit()
            return {"message": "Employee record permanently deleted", "success": True}
        else:
            # Soft delete / deactivation safeguard
            employee.employment_status = "INACTIVE"
            if employee.user:
                employee.user.is_active = False
            db.commit()
            return {"message": "Employee deactivated successfully", "success": True}
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete employee: {str(exc)}"
        )

# ==================== PROFILE AVATAR APPROVAL WORKFLOW ====================

MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_AVATAR_MIMES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}

def request_avatar_update(user_id: int, file: UploadFile, db: Session) -> Employee:
    employee = get_employee_by_user_id(user_id, db)

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_AVATAR_MIMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image type '{content_type}'. Allowed types: JPG, PNG, WEBP."
        )

    base_upload = os.getenv("UPLOAD_DIR", "/tmp/uploads" if os.environ.get("VERCEL") else os.path.join(os.getcwd(), "uploads"))
    upload_dir = os.path.join(base_upload, "avatars")
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    safe_name = f"avatar_{employee.id}_{uuid.uuid4().hex[:8]}{ext}"
    dest_path = os.path.join(upload_dir, safe_name)

    size = 0
    with open(dest_path, "wb") as buffer:
        while chunk := file.file.read(1024 * 64):
            size += len(chunk)
            if size > MAX_AVATAR_SIZE:
                buffer.close()
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Avatar image exceeds maximum allowed size of 5 MB."
                )
            buffer.write(chunk)

    employee.pending_profile_picture = f"/uploads/avatars/{safe_name}"
    employee.profile_picture_status = "PENDING"
    employee.profile_picture_rejection_reason = None
    employee.profile_picture_updated_at = datetime.now()

    # Create administrative notification for all Admins & Super Admins
    admins = db.query(User).filter(User.role.in_(["ADMIN", "SUPER_ADMIN"]), User.is_active == True).all()
    for adm in admins:
        notif = Notification(
            user_id=adm.id,
            title="Profile Photo Approval Request",
            message=f"{employee.full_name} ({employee.employee_code}) submitted a new profile picture awaiting HR approval.",
            type="AVATAR_REQUEST",
            is_read=False
        )
        db.add(notif)

    log_audit(
        db=db,
        user_id=user_id,
        action="AVATAR_UPDATE_REQUESTED",
        resource_type="EMPLOYEE",
        resource_id=str(employee.id),
        details=f"Avatar upload requested: {safe_name}"
    )

    db.commit()
    db.refresh(employee)
    return employee

def get_pending_avatar_requests(db: Session) -> List[AvatarPendingRequestResponse]:
    employees = db.query(Employee).options(
        joinedload(Employee.department)
    ).filter(
        Employee.profile_picture_status == "PENDING",
        Employee.pending_profile_picture.isnot(None)
    ).order_by(Employee.profile_picture_updated_at.desc()).all()

    results = []
    for emp in employees:
        dept_name = emp.department.name if emp.department else "N/A"
        results.append(AvatarPendingRequestResponse(
            employee_id=emp.id,
            employee_code=emp.employee_code,
            full_name=emp.full_name,
            department_name=dept_name,
            current_avatar=emp.profile_picture,
            current_profile_picture=emp.profile_picture,
            pending_avatar=emp.pending_profile_picture,
            pending_profile_picture=emp.pending_profile_picture,
            status=emp.profile_picture_status or "PENDING",
            profile_picture_status=emp.profile_picture_status or "PENDING",
            submitted_at=emp.profile_picture_updated_at
        ))
    return results

def review_avatar_request(
    employee_id: int,
    status_decision: str,
    rejection_reason: Optional[str],
    admin_user_id: int,
    db: Session
) -> Employee:
    employee = get_employee_by_id(employee_id, db)
    if employee.profile_picture_status != "PENDING" or not employee.pending_profile_picture:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This employee does not have a pending profile picture request."
        )

    decision = status_decision.upper().strip()
    if decision not in ["APPROVED", "REJECTED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be either 'APPROVED' or 'REJECTED'."
        )

    if decision == "APPROVED":
        employee.profile_picture = employee.pending_profile_picture
        employee.pending_profile_picture = None
        employee.profile_picture_status = "APPROVED"
        employee.profile_picture_rejection_reason = None
        employee.profile_picture_updated_at = datetime.now()

        # Notify employee
        notif = Notification(
            user_id=employee.user_id,
            title="Profile Photo Approved",
            message="Your updated profile picture has been approved by HR and is now active across WorkPulse.",
            type="AVATAR_APPROVED",
            is_read=False
        )
        db.add(notif)
        log_audit(
            db=db,
            user_id=admin_user_id,
            action="AVATAR_APPROVED",
            resource_type="EMPLOYEE",
            resource_id=str(employee.id),
            details=f"Avatar approved for {employee.full_name}"
        )
    else:
        employee.profile_picture_status = "REJECTED"
        employee.profile_picture_rejection_reason = (rejection_reason or "Does not comply with corporate photo guidelines.").strip()
        employee.pending_profile_picture = None
        employee.profile_picture_updated_at = datetime.now()

        # Notify employee
        notif = Notification(
            user_id=employee.user_id,
            title="Profile Photo Declined",
            message=f"Your profile picture update was declined by HR. Reason: {employee.profile_picture_rejection_reason}",
            type="AVATAR_REJECTED",
            is_read=False
        )
        db.add(notif)
        log_audit(
            db=db,
            user_id=admin_user_id,
            action="AVATAR_REJECTED",
            resource_type="EMPLOYEE",
            resource_id=str(employee.id),
            details=f"Avatar rejected: {employee.profile_picture_rejection_reason}"
        )

    db.commit()
    db.refresh(employee)
    return employee
