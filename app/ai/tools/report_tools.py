from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai import AIAuditLog, AIUsageLog
from app.models.audit_log import AuditLog
from app.models.user import User


def get_system_audit_summary(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    """Return recent system & AI audit activity counts (Super Admin / Auditor only)."""
    days = min(max(int(args.get("days", 7)), 1), 30)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    ems_events = db.query(func.count(AuditLog.id)).filter(AuditLog.created_at >= since).scalar() or 0
    ai_events = (
        db.query(func.count(AIAuditLog.id))
        .filter(
            AIAuditLog.organization_id == user.organization_id,
            AIAuditLog.created_at >= since,
        )
        .scalar()
        or 0
    )
    ai_tokens = (
        db.query(func.coalesce(func.sum(AIUsageLog.total_tokens), 0))
        .filter(
            AIUsageLog.organization_id == user.organization_id,
            AIUsageLog.created_at >= since,
        )
        .scalar()
        or 0
    )
    return {
        "period_days": days,
        "ems_audit_events": int(ems_events),
        "ai_audit_events": int(ai_events),
        "ai_tokens_used": int(ai_tokens),
    }
