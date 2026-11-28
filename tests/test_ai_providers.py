import asyncio
import json
import pytest
import httpx

from app.ai.config import AISettings, get_ai_settings
from app.ai.providers import get_ai_provider
from app.ai.providers.base import AIMessageInput, AIProviderError, AIToolDefinition
from app.ai.providers.gemini import GeminiProvider
from app.models.ai import (
    AIAuditLog,
    AIConversation,
    AIDocument,
    AIDocumentChunk,
    AIMessage,
    AIMessageFeedback,
    AIProviderConfig,
    AIUsageLog,
)
from app.models.organization import Organization


def test_ai_settings_safe_defaults(monkeypatch):
    monkeypatch.delenv("AI_ENABLED", raising=False)
    monkeypatch.delenv("AI_DEFAULT_PROVIDER", raising=False)
    monkeypatch.delenv("AI_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = get_ai_settings()
    assert settings.enabled is False
    assert settings.default_provider == "gemini"
    assert settings.default_model == "gemini-3.0-flash"
    assert settings.has_provider_credentials("gemini") is False


def test_ai_models_persist_in_db(db_session, employee_user):
    org = Organization(
        name="Nexora Test Org",
        slug="nexora-test-org",
        company_code="NEX-TST",
    )
    db_session.add(org)
    db_session.flush()

    conv = AIConversation(
        organization_id=org.id,
        user_id=employee_user.id,
        title="Leave balance check",
        provider="gemini",
        model="gemini-2.5-flash",
    )
    db_session.add(conv)
    db_session.flush()

    msg = AIMessage(
        conversation_id=conv.id,
        organization_id=org.id,
        user_id=employee_user.id,
        role="assistant",
        content="You have 12 annual leave days remaining.",
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
    )
    db_session.add(msg)
    db_session.flush()

    fb = AIMessageFeedback(
        message_id=msg.id,
        user_id=employee_user.id,
        organization_id=org.id,
        rating="positive",
    )
    doc = AIDocument(
        organization_id=org.id,
        uploaded_by=employee_user.id,
        title="Leave Policy 2026",
        filename="leave_policy.pdf",
        content_type="application/pdf",
        status="indexed",
        chunk_count=1,
    )
    db_session.add_all([fb, doc])
    db_session.flush()

    chunk = AIDocumentChunk(
        document_id=doc.id,
        organization_id=org.id,
        chunk_index=0,
        content="Employees receive 18 days of annual leave.",
        embedding=[0.1, 0.2, 0.3],
    )
    usage = AIUsageLog(
        organization_id=org.id,
        user_id=employee_user.id,
        conversation_id=conv.id,
        provider="gemini",
        model="gemini-2.5-flash",
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
    )
    audit = AIAuditLog(
        organization_id=org.id,
        user_id=employee_user.id,
        conversation_id=conv.id,
        action="chat_request",
        output_status="success",
    )
    cfg = AIProviderConfig(organization_id=org.id, is_enabled=False)
    db_session.add_all([chunk, usage, audit, cfg])
    db_session.commit()

    assert db_session.query(AIConversation).count() == 1
    assert db_session.query(AIMessage).count() == 1
    assert db_session.query(AIDocumentChunk).first().embedding == [0.1, 0.2, 0.3]


def test_provider_factory_resolution():
    provider = get_ai_provider("gemini")
    assert isinstance(provider, GeminiProvider)

    for name in ("openai", "anthropic", "groq", "deepseek", "ollama"):
        resolved = get_ai_provider(name)
        assert resolved.provider_name == name

    with pytest.raises(AIProviderError) as exc_info:
        get_ai_provider("unknown_llm")
    assert exc_info.value.code == "unsupported_provider"


def test_multi_provider_mocked_generate(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "OpenAI-compat ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
                },
            )
        if request.url.path.endswith("/v1/messages"):
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "Anthropic ok"}],
                    "usage": {"input_tokens": 4, "output_tokens": 2},
                    "stop_reason": "end_turn",
                },
            )
        if request.url.path.endswith("/api/chat"):
            return httpx.Response(
                200,
                json={
                    "message": {"content": "Ollama ok"},
                    "prompt_eval_count": 3,
                    "eval_count": 2,
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real_async_client(*a, **{**kw, "transport": transport}))

    settings = AISettings(
        enabled=True,
        default_provider="gemini",
        default_model="gemini-2.5-flash",
        default_embedding_model="text-embedding-004",
        request_timeout_seconds=10.0,
        max_tokens_per_request=1024,
        daily_user_token_limit=10000,
        max_context_messages=10,
        temperature=0.2,
        gemini_api_key="k1",
        gemini_base_url="https://generativelanguage.googleapis.com/v1beta",
        openai_api_key="k2",
        anthropic_api_key="k3",
        groq_api_key="k4",
        deepseek_api_key="k5",
        ollama_base_url="http://localhost:11434",
    )

    async def run_all():
        for name, expected in [
            ("openai", "OpenAI-compat ok"),
            ("groq", "OpenAI-compat ok"),
            ("deepseek", "OpenAI-compat ok"),
            ("anthropic", "Anthropic ok"),
            ("ollama", "Ollama ok"),
        ]:
            prov = get_ai_provider(name, settings)
            res = await prov.generate([AIMessageInput(role="user", content="Ping")])
            assert res.content == expected
            assert res.usage.total_tokens > 0

    asyncio.run(run_all())


def test_gemini_requires_api_key():
    settings = AISettings(
        enabled=True,
        default_provider="gemini",
        default_model="gemini-2.5-flash",
        default_embedding_model="text-embedding-004",
        request_timeout_seconds=10.0,
        max_tokens_per_request=1024,
        daily_user_token_limit=10000,
        max_context_messages=10,
        temperature=0.3,
        gemini_api_key=None,
        gemini_base_url="https://generativelanguage.googleapis.com/v1beta",
        openai_api_key=None,
        anthropic_api_key=None,
        groq_api_key=None,
        deepseek_api_key=None,
        ollama_base_url="http://localhost:11434",
    )
    provider = GeminiProvider(settings)
    with pytest.raises(AIProviderError) as exc_info:
        asyncio.run(provider.generate([AIMessageInput(role="user", content="Hi")]))
    assert exc_info.value.code == "missing_api_key"


def test_gemini_generate_stream_and_embed_mocked(monkeypatch):
    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append((str(request.url), request.headers.get("x-goog-api-key")))
        if request.url.path.endswith(":generateContent"):
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": "Checking leave balance."},
                                    {
                                        "functionCall": {
                                            "name": "get_my_leave_balance",
                                            "args": {"year": 2026},
                                        }
                                    },
                                ]
                            },
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 15,
                        "candidatesTokenCount": 8,
                        "totalTokenCount": 23,
                    },
                },
            )
        if request.url.path.endswith(":streamGenerateContent"):
            sse_body = (
                'data: {"candidates":[{"content":{"parts":[{"text":"Hello "}]}}]}\n\n'
                'data: {"candidates":[{"content":{"parts":[{"text":"Nexora!"}]},"finishReason":"STOP"}],'
                '"usageMetadata":{"promptTokenCount":5,"candidatesTokenCount":2,"totalTokenCount":7}}\n\n'
            )
            return httpx.Response(200, content=sse_body.encode("utf-8"))
        if request.url.path.endswith(":batchEmbedContents"):
            return httpx.Response(
                200,
                json={"embeddings": [{"values": [0.25, 0.5, 0.75]}]},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)

    settings = AISettings(
        enabled=True,
        default_provider="gemini",
        default_model="gemini-2.5-flash",
        default_embedding_model="text-embedding-004",
        request_timeout_seconds=10.0,
        max_tokens_per_request=1024,
        daily_user_token_limit=10000,
        max_context_messages=10,
        temperature=0.2,
        gemini_api_key="test-key-not-real",
        gemini_base_url="https://generativelanguage.googleapis.com/v1beta",
        openai_api_key=None,
        anthropic_api_key=None,
        groq_api_key=None,
        deepseek_api_key=None,
        ollama_base_url="http://localhost:11434",
    )
    provider = GeminiProvider(settings)

    async def run_checks():
        res = await provider.generate(
            [AIMessageInput(role="user", content="What is my leave balance?")],
            system_prompt="You are Nexora Copilot.",
            tools=[
                AIToolDefinition(
                    name="get_my_leave_balance",
                    description="Get current user's leave balance",
                    parameters={"type": "object", "properties": {"year": {"type": "integer"}}},
                )
            ],
        )
        assert res.content == "Checking leave balance."
        assert len(res.tool_calls) == 1
        assert res.tool_calls[0].name == "get_my_leave_balance"
        assert res.tool_calls[0].arguments == {"year": 2026}
        assert res.usage.total_tokens == 23

        chunks = []
        async for chunk in provider.stream([AIMessageInput(role="user", content="Hi")]):
            chunks.append(chunk)
        assert "".join(c.delta_text for c in chunks) == "Hello Nexora!"
        assert chunks[-1].done is True
        assert chunks[-1].usage.total_tokens == 7

        vectors = await provider.embed(["Annual leave policy"])
        assert vectors == [[0.25, 0.5, 0.75]]

    asyncio.run(run_checks())
    assert all(hdr == "test-key-not-real" for _, hdr in captured_requests)
