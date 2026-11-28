from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai.config import get_ai_settings
from app.ai.guardrails import check_user_quota, record_ai_audit
from app.ai.orchestrator import get_or_create_org_config, run_chat, stream_chat
from app.ai.providers import SUPPORTED_PROVIDERS
from app.ai.tools import get_authorized_tools
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_admin
from app.models.ai import (
    AIAuditLog,
    AIConversation,
    AIMessage,
    AIMessageFeedback,
    AIUsageLog,
)
from app.models.user import User
from app.schemas.ai import (
    AIChatRequest,
    AIChatResponse,
    AIConversationOut,
    AIConversationUpdate,
    AIFeedbackCreate,
    AIMessageOut,
    AIProviderConfigOut,
    AIProviderConfigUpdate,
)

router = APIRouter()


@router.get("/status")
def get_ai_status(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Return non-secret Nexora AI availability, active model, and user's authorized tools."""
    settings = get_ai_settings()
    config = get_or_create_org_config(db, current_user.organization_id)
    has_creds = settings.has_provider_credentials(config.active_provider)
    quota = check_user_quota(db, current_user, config.daily_user_token_limit)
    tools = get_authorized_tools(current_user) if config.allow_tools else []
    return {
        "enabled": bool(settings.enabled and config.is_enabled and has_creds),
        "server_enabled": settings.enabled,
        "org_enabled": config.is_enabled,
        "has_credentials": has_creds,
        "active_provider": config.active_provider,
        "active_model": config.active_model,
        "allow_general_chat": config.allow_general_chat,
        "allow_rag": config.allow_rag,
        "allow_tools": config.allow_tools,
        "quota": quota,
        "available_tools": [t.name for t in tools],
    }


@router.post("/chat", response_model=AIChatResponse)
async def chat_with_copilot(
    payload: AIChatRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Send a message to Nexora Copilot and receive a structured response."""
    ip_address = request.client.host if request.client else None
    conv, assistant_msg = await run_chat(
        db,
        current_user,
        message=payload.message,
        conversation_id=payload.conversation_id,
        provider_override=payload.provider,
        model_override=payload.model,
        ip_address=ip_address,
    )
    return AIChatResponse(
        conversation_id=conv.id,
        conversation_title=conv.title,
        message=AIMessageOut.model_validate(assistant_msg),
    )


@router.post("/chat/stream")
async def stream_chat_with_copilot(
    payload: AIChatRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Stream Nexora Copilot responses over Server-Sent Events (SSE)."""
    ip_address = request.client.host if request.client else None
    generator = stream_chat(
        db,
        current_user,
        message=payload.message,
        conversation_id=payload.conversation_id,
        provider_override=payload.provider,
        model_override=payload.model,
        ip_address=ip_address,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", response_model=list[AIConversationOut])
def list_conversations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, max_length=120),
    include_archived: bool = Query(default=False),
):
    """List the authenticated user's AI conversations."""
    query = db.query(AIConversation).filter(
        AIConversation.user_id == current_user.id,
        AIConversation.organization_id == current_user.organization_id,
    )
    if not include_archived:
        query = query.filter(AIConversation.is_archived == False)  # noqa: E712
    if search:
        query = query.filter(AIConversation.title.ilike(f"%{search.strip()}%"))

    return (
        query.order_by(
            AIConversation.is_pinned.desc(),
            AIConversation.last_message_at.desc(),
            AIConversation.updated_at.desc(),
        )
        .limit(100)
        .all()
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[AIMessageOut])
def get_conversation_messages(
    conversation_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Fetch messages for a conversation owned by the current user."""
    conv = (
        db.query(AIConversation)
        .filter(
            AIConversation.id == conversation_id,
            AIConversation.user_id == current_user.id,
            AIConversation.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return (
        db.query(AIMessage)
        .filter(AIMessage.conversation_id == conv.id)
        .order_by(AIMessage.created_at.asc(), AIMessage.id.asc())
        .all()
    )


@router.patch("/conversations/{conversation_id}", response_model=AIConversationOut)
def update_conversation(
    conversation_id: int,
    payload: AIConversationUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Rename, pin, or archive a conversation owned by the current user."""
    conv = (
        db.query(AIConversation)
        .filter(
            AIConversation.id == conversation_id,
            AIConversation.user_id == current_user.id,
            AIConversation.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    if payload.title is not None:
        conv.title = payload.title.strip()
    if payload.is_pinned is not None:
        conv.is_pinned = payload.is_pinned
    if payload.is_archived is not None:
        conv.is_archived = payload.is_archived
    db.commit()
    db.refresh(conv)
    return conv


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_200_OK)
def delete_conversation(
    conversation_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Delete a conversation owned by the current user."""
    conv = (
        db.query(AIConversation)
        .filter(
            AIConversation.id == conversation_id,
            AIConversation.user_id == current_user.id,
            AIConversation.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    db.delete(conv)
    db.commit()
    return {"deleted": True, "conversation_id": conversation_id}


@router.post("/messages/{message_id}/feedback")
def submit_message_feedback(
    message_id: int,
    payload: AIFeedbackCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Record thumbs-up or thumbs-down feedback on an assistant message."""
    msg = (
        db.query(AIMessage)
        .filter(
            AIMessage.id == message_id,
            AIMessage.user_id == current_user.id,
            AIMessage.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")

    fb = AIMessageFeedback(
        message_id=msg.id,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return {"id": fb.id, "message_id": msg.id, "rating": fb.rating}


@router.get("/config")
def get_ai_config(
    current_user: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """Admin endpoint to view active AI provider configuration and supported catalog."""
    settings = get_ai_settings()
    cfg = get_or_create_org_config(db, current_user.organization_id)
    return {
        "config": AIProviderConfigOut.model_validate(cfg),
        "providers": {
            name: {
                **meta,
                "has_credentials": settings.has_provider_credentials(name),
            }
            for name, meta in SUPPORTED_PROVIDERS.items()
        },
        "server_ai_enabled": settings.enabled,
    }


@router.put("/config", response_model=AIProviderConfigOut)
def update_ai_config(
    payload: AIProviderConfigUpdate,
    request: Request,
    current_user: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """Admin endpoint to configure active provider, model, feature toggles, and quotas."""
    cfg = get_or_create_org_config(db, current_user.organization_id)
    if payload.active_provider is not None:
        p_name = payload.active_provider.strip().lower()
        if p_name not in SUPPORTED_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Unsupported provider '{p_name}'.")
        cfg.active_provider = p_name
    if payload.active_model is not None:
        cfg.active_model = payload.active_model.strip()
    if payload.embedding_model is not None:
        cfg.embedding_model = payload.embedding_model.strip()
    if payload.is_enabled is not None:
        cfg.is_enabled = payload.is_enabled
    if payload.allow_general_chat is not None:
        cfg.allow_general_chat = payload.allow_general_chat
    if payload.allow_rag is not None:
        cfg.allow_rag = payload.allow_rag
    if payload.allow_tools is not None:
        cfg.allow_tools = payload.allow_tools
    if payload.max_tokens_per_request is not None:
        cfg.max_tokens_per_request = payload.max_tokens_per_request
    if payload.daily_user_token_limit is not None:
        cfg.daily_user_token_limit = payload.daily_user_token_limit
    if payload.temperature is not None:
        cfg.temperature = payload.temperature

    cfg.updated_by = current_user.id
    record_ai_audit(
        db,
        user=current_user,
        action="config_update",
        input_summary=f"provider={cfg.active_provider} model={cfg.active_model} enabled={cfg.is_enabled}",
        output_status="success",
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(cfg)
    return cfg


@router.get("/usage")
def get_ai_usage_summary(
    current_user: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """Admin endpoint to monitor organization AI token usage and recent audit events."""
    org_id = current_user.organization_id
    totals = (
        db.query(
            func.count(AIUsageLog.id),
            func.coalesce(func.sum(AIUsageLog.prompt_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.completion_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.total_tokens), 0),
        )
        .filter(AIUsageLog.organization_id == org_id)
        .one()
    )
    recent_audits = (
        db.query(AIAuditLog)
        .filter(AIAuditLog.organization_id == org_id)
        .order_by(AIAuditLog.created_at.desc(), AIAuditLog.id.desc())
        .limit(20)
        .all()
    )
    return {
        "total_requests": int(totals[0] or 0),
        "prompt_tokens": int(totals[1] or 0),
        "completion_tokens": int(totals[2] or 0),
        "total_tokens": int(totals[3] or 0),
        "recent_audits": [
            {
                "id": a.id,
                "user_id": a.user_id,
                "action": a.action,
                "tool_name": a.tool_name,
                "output_status": a.output_status,
                "created_at": a.created_at.isoformat(),
            }
            for a in recent_audits
        ],
    }
