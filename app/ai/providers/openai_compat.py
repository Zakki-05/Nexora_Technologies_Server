import json
from typing import Any, AsyncIterator

import httpx

from app.ai.config import AISettings
from app.ai.providers.base import (
    AICompletionResponse,
    AIMessageInput,
    AIProviderBase,
    AIProviderError,
    AIStreamChunk,
    AIToolCall,
    AIToolDefinition,
    AIUsage,
)


class OpenAICompatibleProvider(AIProviderBase):
    """Shared adapter for OpenAI-compatible Chat Completions APIs (OpenAI, Groq, DeepSeek)."""

    def __init__(
        self,
        settings: AISettings,
        *,
        provider_name: str,
        base_url: str,
        api_key: str | None,
        default_model: str,
        supports_embeddings: bool = False,
    ) -> None:
        self._settings = settings
        self.provider_name = provider_name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        self._supports_embeddings = supports_embeddings

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise AIProviderError(
                f"{self.provider_name.title()} API key is not configured on the backend.",
                code="missing_api_key",
                status_code=503,
            )
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

    @staticmethod
    def _to_messages(
        messages: list[AIMessageInput], system_prompt: str | None
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if system_prompt:
            out.append({"role": "system", "content": system_prompt})
        for msg in messages:
            if msg.role == "tool":
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id or msg.tool_name or "tool_call",
                        "content": msg.content,
                    }
                )
            else:
                out.append({"role": msg.role, "content": msg.content})
        return out

    @staticmethod
    def _to_tools(tools: list[AIToolDefinition] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        code = "provider_error"
        if response.status_code in (401, 403):
            code = "provider_auth_error"
        elif response.status_code == 429:
            code = "provider_rate_limited"
        try:
            detail = response.json().get("error", {}).get("message")
        except Exception:
            detail = None
        raise AIProviderError(
            detail or f"{self.provider_name} API returned status {response.status_code}.",
            code=code,
            status_code=502 if response.status_code >= 500 else response.status_code,
        )

    async def generate(
        self,
        messages: list[AIMessageInput],
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        tools: list[AIToolDefinition] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        response_schema: dict[str, Any] | None = None,
    ) -> AICompletionResponse:
        target_model = model or self._default_model
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": self._to_messages(messages, system_prompt),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        formatted_tools = self._to_tools(tools)
        if formatted_tools:
            payload["tools"] = formatted_tools
        if response_schema is not None:
            payload["response_format"] = {"type": "json_object"}

        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise AIProviderError(f"{self.provider_name} request timed out.", code="provider_timeout", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Unable to reach {self.provider_name} API.", code="provider_unreachable", status_code=502) from exc

        self._raise_for_status(response)
        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls: list[AIToolCall] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            raw_args = fn.get("arguments") or "{}"
            try:
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                parsed_args = {}
            tool_calls.append(
                AIToolCall(
                    name=fn.get("name", ""),
                    arguments=parsed_args,
                    call_id=tc.get("id"),
                )
            )

        usage_raw = data.get("usage") or {}
        usage = AIUsage(
            prompt_tokens=int(usage_raw.get("prompt_tokens") or 0),
            completion_tokens=int(usage_raw.get("completion_tokens") or 0),
            total_tokens=int(usage_raw.get("total_tokens") or 0),
        )
        content = msg.get("content") or ""
        structured_data = None
        if response_schema is not None and content.strip():
            try:
                structured_data = json.loads(content)
            except json.JSONDecodeError:
                structured_data = None

        return AICompletionResponse(
            content=content,
            provider=self.provider_name,
            model=target_model,
            usage=usage,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason"),
            structured_data=structured_data,
        )

    async def stream(
        self,
        messages: list[AIMessageInput],
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        tools: list[AIToolDefinition] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncIterator[AIStreamChunk]:
        target_model = model or self._default_model
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": self._to_messages(messages, system_prompt),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        formatted_tools = self._to_tools(tools)
        if formatted_tools:
            payload["tools"] = formatted_tools

        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    self._raise_for_status(response)
                    async for raw_line in response.aiter_lines():
                        line = raw_line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        raw_json = line[5:].strip()
                        if raw_json == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(raw_json)
                        except json.JSONDecodeError:
                            continue
                        choice = (chunk_data.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}
                        text = delta.get("content") or ""
                        if text:
                            yield AIStreamChunk(delta_text=text, done=False)
                    yield AIStreamChunk(delta_text="", done=True, usage=AIUsage(), finish_reason="stop")
        except httpx.TimeoutException as exc:
            raise AIProviderError(f"{self.provider_name} stream timed out.", code="provider_timeout", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Unable to reach {self.provider_name} stream API.", code="provider_unreachable", status_code=502) from exc

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        if not texts:
            return []
        if not self._supports_embeddings:
            raise AIProviderError(
                f"Embeddings are not supported for provider '{self.provider_name}'.",
                code="embeddings_unsupported",
                status_code=400,
            )
        target_model = model or "text-embedding-3-small"
        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/embeddings",
                    headers=self._headers(),
                    json={"model": target_model, "input": texts},
                )
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Unable to reach {self.provider_name} embeddings API.", code="provider_unreachable", status_code=502) from exc
        self._raise_for_status(response)
        data = response.json()
        return [item.get("embedding") or [] for item in (data.get("data") or [])]
