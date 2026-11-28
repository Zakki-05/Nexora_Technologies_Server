import re
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai import AIAuditLog, AIUsageLog
from app.models.user import User

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+prompt|api\s*key|secret|database\s+password)", re.IGNORECASE),
    re.compile(r"(execute|run|drop|delete|truncate)\s+(raw\s+)?sql", re.IGNORECASE),
    re.compile(r"bypass\s+(rbac|permissions|role|auth|security)", re.IGNORECASE),
]

_SECRET_PATTERNS = [
    (re.compile(r"Bearer\s+[A-Za-z0-9\-_\.]+", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{20,}"), "[REDACTED_GEMINI_KEY]"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"(password|secret|token)\s*[:=]\s*\S+", re.IGNORECASE), r"\1=[REDACTED]"),
]


class GuardrailViolation(Exception):
    """Raised when a prompt or quota guardrail blocks a request."""

    def __init__(self, message: str, *, code: str = "guardrail_blocked", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def detect_prompt_injection(text: str) -> str | None:
    """Return matched pattern description if text looks like an injection attempt."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return pattern.pattern
    return None


def redact_sensitive_text(text: str) -> str:
    """Scrub secret tokens and API keys from text before logging or forwarding."""
    redacted = text
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def summarize_for_audit(text: str, max_len: int = 240) -> str:
    """Create a redacted, bounded summary suitable for ai_audit_logs."""
    cleaned = redact_sensitive_text(text).strip().replace("\n", " ")
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3] + "..."


def check_user_quota(
    db: Session,
    user: User,
    daily_token_limit: int,
    max_requests_per_minute: int = 20,
) -> dict[str, int]:
    """Enforce daily token budget and per-minute rate limit for a user."""
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    minute_ago = now - timedelta(minutes=1)

    tokens_today = (
        db.query(func.coalesce(func.sum(AIUsageLog.total_tokens), 0))
        .filter(
            AIUsageLog.user_id == user.id,
            AIUsageLog.organization_id == user.organization_id,
            AIUsageLog.created_at >= day_start,
        )
        .scalar()
        or 0
    )

    if int(tokens_today) >= daily_token_limit:
        raise GuardrailViolation(
            f"Daily AI token limit ({daily_token_limit:,}) reached. Please try again tomorrow.",
            code="daily_quota_exceeded",
            status_code=429,
        )

    recent_requests = (
        db.query(func.count(AIUsageLog.id))
        .filter(
            AIUsageLog.user_id == user.id,
            AIUsageLog.organization_id == user.organization_id,
            AIUsageLog.created_at >= minute_ago,
        )
        .scalar()
        or 0
    )

    if int(recent_requests) >= max_requests_per_minute:
        raise GuardrailViolation(
            "Too many AI requests in a short window. Please wait a moment.",
            code="rate_limit_exceeded",
            status_code=429,
        )

    return {
        "tokens_used_today": int(tokens_today),
        "daily_token_limit": daily_token_limit,
        "remaining_tokens_today": max(0, daily_token_limit - int(tokens_today)),
    }


def record_ai_audit(
    db: Session,
    *,
    user: User,
    action: str,
    conversation_id: int | None = None,
    tool_name: str | None = None,
    input_summary: str | None = None,
    output_status: str = "success",
    ip_address: str | None = None,
) -> None:
    """Persist an immutable AI audit log entry."""
    entry = AIAuditLog(
        organization_id=user.organization_id,
        user_id=user.id,
        conversation_id=conversation_id,
        action=action,
        tool_name=tool_name,
        input_summary=summarize_for_audit(input_summary) if input_summary else None,
        output_status=output_status,
        ip_address=ip_address,
    )
    db.add(entry)
    db.flush()
