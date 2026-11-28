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


class AnthropicProvider(AIProviderBase):
    """Anthropic Claude Messages API adapter using httpx."""

    provider_name = "anthropic"

    def __init__(self, settings: AISettings) -> None:
        self._settings = settings

    def _headers(self) -> dict[str, str]:
        if not self._settings.anthropic_api_key:
            raise AIProviderError(
                "Anthropic API key is not configured on the backend.",
                code="missing_api_key",
                status_code=503,
            )
        return {
            "Content-Type": "application/json",
            "x-api-key": self._settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
        }

    @staticmethod
    def _to_messages(messages: list[AIMessageInput]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "system":
                continue
            role = "assistant" if msg.role == "assistant" else "user"
            out.append({"role": role, "content": msg.content})
        return out

    @staticmethod
    def _to_tools(tools: list[AIToolDefinition] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

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
        target_model = model or "claude-3-5-sonnet-latest"
        payload: dict[str, Any] = {
            "model": target_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": self._to_messages(messages),
        }
        if system_prompt:
            payload["system"] = system_prompt
        formatted_tools = self._to_tools(tools)
        if formatted_tools:
            payload["tools"] = formatted_tools

        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise AIProviderError("Anthropic request timed out.", code="provider_timeout", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("Unable to reach Anthropic API.", code="provider_unreachable", status_code=502) from exc

        if response.status_code >= 400:
            raise AIProviderError(
                f"Anthropic API returned status {response.status_code}.",
                code="provider_error",
                status_code=502 if response.status_code >= 500 else response.status_code,
            )

        data = response.json()
        text_parts: list[str] = []
        tool_calls: list[AIToolCall] = []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    AIToolCall(
                        name=block.get("name") or "",
                        arguments=block.get("input") or {},
                        call_id=block.get("id"),
                    )
                )

        usage_raw = data.get("usage") or {}
        in_tok = int(usage_raw.get("input_tokens") or 0)
        out_tok = int(usage_raw.get("output_tokens") or 0)
        return AICompletionResponse(
            content="".join(text_parts),
            provider=self.provider_name,
            model=target_model,
            usage=AIUsage(prompt_tokens=in_tok, completion_tokens=out_tok, total_tokens=in_tok + out_tok),
            tool_calls=tool_calls,
            finish_reason=data.get("stop_reason"),
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
        target_model = model or "claude-3-5-sonnet-latest"
        payload: dict[str, Any] = {
            "model": target_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": self._to_messages(messages),
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt
        formatted_tools = self._to_tools(tools)
        if formatted_tools:
            payload["tools"] = formatted_tools

        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    "https://api.anthropic.com/v1/messages",
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        raise AIProviderError(
                            f"Anthropic stream returned status {response.status_code}.",
                            code="provider_error",
                            status_code=502 if response.status_code >= 500 else response.status_code,
                        )
                    async for raw_line in response.aiter_lines():
                        line = raw_line.strip()
                        if not line.startswith("data:"):
                            continue
                        try:
                            evt = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            continue
                        if evt.get("type") == "content_block_delta":
                            delta = evt.get("delta") or {}
                            if delta.get("type") == "text_delta" and delta.get("text"):
                                yield AIStreamChunk(delta_text=delta["text"], done=False)
                    yield AIStreamChunk(delta_text="", done=True, usage=AIUsage(), finish_reason="end_turn")
        except httpx.TimeoutException as exc:
            raise AIProviderError("Anthropic stream timed out.", code="provider_timeout", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("Unable to reach Anthropic stream API.", code="provider_unreachable", status_code=502) from exc

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        raise AIProviderError(
            "Anthropic does not provide a native embeddings endpoint.",
            code="embeddings_unsupported",
            status_code=400,
        )
