import json
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.ai.config import AISettings, get_ai_settings
from app.ai.guardrails import (
    GuardrailViolation,
    check_user_quota,
    detect_prompt_injection,
    record_ai_audit,
    redact_sensitive_text,
)
from app.ai.prompts import build_system_prompt
from app.ai.providers import get_ai_provider
from app.ai.providers.base import AIMessageInput, AIProviderError
from app.ai.streaming import format_sse_event
from app.ai.tools import execute_authorized_tool, get_authorized_tools
from app.models.ai import AIConversation, AIMessage, AIProviderConfig, AIUsageLog
from app.models.user import User


def get_or_create_org_config(db: Session, organization_id: int) -> AIProviderConfig:
    """Fetch organization AI config or initialize a safe disabled default."""
    cfg = (
        db.query(AIProviderConfig)
        .filter(AIProviderConfig.organization_id == organization_id)
        .first()
    )
    if cfg is None:
        settings = get_ai_settings()
        cfg = AIProviderConfig(
            organization_id=organization_id,
            active_provider=settings.default_provider,
            active_model=settings.default_model,
            embedding_model=settings.default_embedding_model,
            is_enabled=False,
            max_tokens_per_request=settings.max_tokens_per_request,
            daily_user_token_limit=settings.daily_user_token_limit,
            temperature=settings.temperature,
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def ensure_ai_available(
    settings: AISettings,
    config: AIProviderConfig,
    provider_name: str,
) -> None:
    """Verify server-side AI activation and provider credentials before calling an LLM."""
    if not settings.enabled or not config.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nexora AI is currently disabled by administrator configuration.",
        )
    if not settings.has_provider_credentials(provider_name):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Server credentials for AI provider '{provider_name}' are not configured.",
        )


def _get_or_create_conversation(
    db: Session,
    user: User,
    conversation_id: int | None,
    first_message: str,
    provider_name: str,
    model_name: str,
) -> AIConversation:
    if conversation_id is not None:
        conv = (
            db.query(AIConversation)
            .filter(
                AIConversation.id == conversation_id,
                AIConversation.user_id == user.id,
                AIConversation.organization_id == user.organization_id,
            )
            .first()
        )
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        return conv

    title = first_message.strip().splitlines()[0][:80] or "New Conversation"
    conv = AIConversation(
        organization_id=user.organization_id,
        user_id=user.id,
        title=title,
        provider=provider_name,
        model=model_name,
        last_message_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.flush()
    return conv


def _load_history(
    db: Session,
    conversation_id: int,
    limit: int,
) -> list[AIMessageInput]:
    rows = (
        db.query(AIMessage)
        .filter(AIMessage.conversation_id == conversation_id)
        .order_by(AIMessage.created_at.desc(), AIMessage.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return [AIMessageInput(role=m.role, content=m.content) for m in rows]


def _prepare_chat_context(
    db: Session,
    user: User,
    *,
    message: str,
    conversation_id: int | None,
    provider_override: str | None,
    model_override: str | None,
    ip_address: str | None,
) -> dict[str, Any]:
    settings = get_ai_settings()
    config = get_or_create_org_config(db, user.organization_id)
    provider_name = (provider_override or config.active_provider).strip().lower()
    model_name = (model_override or config.active_model).strip()

    ensure_ai_available(settings, config, provider_name)

    matched = detect_prompt_injection(message)
    if matched:
        record_ai_audit(
            db,
            user=user,
            action="guardrail_block",
            conversation_id=conversation_id,
            input_summary=message,
            output_status="blocked",
            ip_address=ip_address,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request blocked by Nexora AI security guardrails.",
        )

    try:
        check_user_quota(db, user, config.daily_user_token_limit)
    except GuardrailViolation as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    conv = _get_or_create_conversation(
        db, user, conversation_id, message, provider_name, model_name
    )
    safe_message = redact_sensitive_text(message)
    user_msg = AIMessage(
        conversation_id=conv.id,
        organization_id=user.organization_id,
        user_id=user.id,
        role="user",
        content=safe_message,
        provider=provider_name,
        model=model_name,
    )
    db.add(user_msg)
    conv.last_message_at = datetime.now(timezone.utc)
    db.flush()

    history = _load_history(db, conv.id, settings.max_context_messages)
    tools = get_authorized_tools(user) if config.allow_tools else []
    system_prompt = build_system_prompt(
        user,
        tools_enabled=bool(tools),
        rag_enabled=config.allow_rag,
    )
    provider = get_ai_provider(provider_name, settings)

    return {
        "config": config,
        "conv": conv,
        "provider": provider,
        "provider_name": provider_name,
        "model_name": model_name,
        "history": history,
        "tools": tools,
        "system_prompt": system_prompt,
    }


async def run_chat(
    db: Session,
    user: User,
    *,
    message: str,
    conversation_id: int | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
    ip_address: str | None = None,
) -> tuple[AIConversation, AIMessage]:
    """Execute an end-to-end synchronous AI chat turn with RBAC tool calling."""
    ctx = _prepare_chat_context(
        db,
        user,
        message=message,
        conversation_id=conversation_id,
        provider_override=provider_override,
        model_override=model_override,
        ip_address=ip_address,
    )
    conv: AIConversation = ctx["conv"]
    config: AIProviderConfig = ctx["config"]
    provider = ctx["provider"]
    history: list[AIMessageInput] = ctx["history"]
    tools = ctx["tools"]
    system_prompt: str = ctx["system_prompt"]

    started = time.perf_counter()
    recorded_tool_calls: list[dict[str, Any]] = []
    total_prompt = 0
    total_completion = 0

    try:
        response = await provider.generate(
            history,
            model=ctx["model_name"],
            system_prompt=system_prompt,
            tools=tools or None,
            temperature=config.temperature,
            max_tokens=config.max_tokens_per_request,
        )
        total_prompt += response.usage.prompt_tokens
        total_completion += response.usage.completion_tokens

        # Execute up to 3 authorized tool-calling rounds
        rounds = 0
        while response.tool_calls and rounds < 3:
            rounds += 1
            for call in response.tool_calls:
                result = execute_authorized_tool(db, user, call.name, call.arguments)
                recorded_tool_calls.append(
                    {"name": call.name, "arguments": call.arguments, "result": result}
                )
                record_ai_audit(
                    db,
                    user=user,
                    action="tool_call",
                    conversation_id=conv.id,
                    tool_name=call.name,
                    input_summary=json.dumps(call.arguments),
                    output_status="error" if "error" in result else "success",
                    ip_address=ip_address,
                )
                history.append(
                    AIMessageInput(
                        role="tool",
                        tool_name=call.name,
                        content=json.dumps(result, default=str),
                    )
                )

            response = await provider.generate(
                history,
                model=ctx["model_name"],
                system_prompt=system_prompt,
                tools=tools or None,
                temperature=config.temperature,
                max_tokens=config.max_tokens_per_request,
            )
            total_prompt += response.usage.prompt_tokens
            total_completion += response.usage.completion_tokens

    except AIProviderError as exc:
        db.add(
            AIUsageLog(
                organization_id=user.organization_id,
                user_id=user.id,
                conversation_id=conv.id,
                provider=ctx["provider_name"],
                model=ctx["model_name"],
                request_type="chat",
                status="error",
                error_code=exc.code,
            )
        )
        record_ai_audit(
            db,
            user=user,
            action="chat_request",
            conversation_id=conv.id,
            input_summary=message,
            output_status=exc.code,
            ip_address=ip_address,
        )
        db.commit()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    total_tokens = total_prompt + total_completion

    assistant_msg = AIMessage(
        conversation_id=conv.id,
        organization_id=user.organization_id,
        user_id=user.id,
        role="assistant",
        content=response.content,
        provider=ctx["provider_name"],
        model=ctx["model_name"],
        tool_calls=recorded_tool_calls or None,
        prompt_tokens=total_prompt,
        completion_tokens=total_completion,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        status="completed",
    )
    db.add(assistant_msg)
    db.add(
        AIUsageLog(
            organization_id=user.organization_id,
            user_id=user.id,
            conversation_id=conv.id,
            provider=ctx["provider_name"],
            model=ctx["model_name"],
            request_type="chat",
            prompt_tokens=total_prompt,
            completion_tokens=total_completion,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            status="success",
        )
    )
    record_ai_audit(
        db,
        user=user,
        action="chat_request",
        conversation_id=conv.id,
        input_summary=message,
        output_status="success",
        ip_address=ip_address,
    )
    conv.last_message_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_msg)
    db.refresh(conv)
    return conv, assistant_msg


async def stream_chat(
    db: Session,
    user: User,
    *,
    message: str,
    conversation_id: int | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
    ip_address: str | None = None,
) -> AsyncIterator[str]:
    """Stream AI response tokens as SSE frames and persist the final message."""
    ctx = _prepare_chat_context(
        db,
        user,
        message=message,
        conversation_id=conversation_id,
        provider_override=provider_override,
        model_override=model_override,
        ip_address=ip_address,
    )
    conv: AIConversation = ctx["conv"]
    config: AIProviderConfig = ctx["config"]
    provider = ctx["provider"]
    history: list[AIMessageInput] = ctx["history"]
    tools = ctx["tools"]
    system_prompt: str = ctx["system_prompt"]

    yield format_sse_event(
        "meta",
        {
            "conversation_id": conv.id,
            "conversation_title": conv.title,
            "provider": ctx["provider_name"],
            "model": ctx["model_name"],
        },
    )

    started = time.perf_counter()
    accumulated_text: list[str] = []
    recorded_tool_calls: list[dict[str, Any]] = []
    prompt_tokens = 0
    completion_tokens = 0

    try:
        pending_tools = []
        async for chunk in provider.stream(
            history,
            model=ctx["model_name"],
            system_prompt=system_prompt,
            tools=tools or None,
            temperature=config.temperature,
            max_tokens=config.max_tokens_per_request,
        ):
            if chunk.tool_calls:
                pending_tools.extend(chunk.tool_calls)
            if chunk.delta_text:
                accumulated_text.append(chunk.delta_text)
                yield format_sse_event("delta", {"text": chunk.delta_text})
            if chunk.usage:
                prompt_tokens = chunk.usage.prompt_tokens
                completion_tokens = chunk.usage.completion_tokens

        if pending_tools:
            for call in pending_tools:
                result = execute_authorized_tool(db, user, call.name, call.arguments)
                recorded_tool_calls.append(
                    {"name": call.name, "arguments": call.arguments, "result": result}
                )
                yield format_sse_event(
                    "tool_call", {"name": call.name, "arguments": call.arguments}
                )
                history.append(
                    AIMessageInput(
                        role="tool",
                        tool_name=call.name,
                        content=json.dumps(result, default=str),
                    )
                )

            async for chunk in provider.stream(
                history,
                model=ctx["model_name"],
                system_prompt=system_prompt,
                tools=None,
                temperature=config.temperature,
                max_tokens=config.max_tokens_per_request,
            ):
                if chunk.delta_text:
                    accumulated_text.append(chunk.delta_text)
                    yield format_sse_event("delta", {"text": chunk.delta_text})
                if chunk.usage:
                    prompt_tokens += chunk.usage.prompt_tokens
                    completion_tokens += chunk.usage.completion_tokens

    except AIProviderError as exc:
        db.rollback()
        yield format_sse_event("error", {"code": exc.code, "message": exc.message})
        return

    latency_ms = int((time.perf_counter() - started) * 1000)
    total_tokens = prompt_tokens + completion_tokens
    full_text = "".join(accumulated_text)

    assistant_msg = AIMessage(
        conversation_id=conv.id,
        organization_id=user.organization_id,
        user_id=user.id,
        role="assistant",
        content=full_text,
        provider=ctx["provider_name"],
        model=ctx["model_name"],
        tool_calls=recorded_tool_calls or None,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        status="completed",
    )
    db.add(assistant_msg)
    db.add(
        AIUsageLog(
            organization_id=user.organization_id,
            user_id=user.id,
            conversation_id=conv.id,
            provider=ctx["provider_name"],
            model=ctx["model_name"],
            request_type="stream",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            status="success",
        )
    )
    record_ai_audit(
        db,
        user=user,
        action="chat_stream",
        conversation_id=conv.id,
        input_summary=message,
        output_status="success",
        ip_address=ip_address,
    )
    conv.last_message_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_msg)

    yield format_sse_event(
        "done",
        {
            "conversation_id": conv.id,
            "message_id": assistant_msg.id,
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
        },
    )
