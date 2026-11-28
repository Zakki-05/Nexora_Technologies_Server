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
    AIToolDefinition,
    AIUsage,
)


class OllamaProvider(AIProviderBase):
    """Local/self-hosted Ollama REST adapter using httpx."""

    provider_name = "ollama"

    def __init__(self, settings: AISettings) -> None:
        self._settings = settings

    @staticmethod
    def _to_messages(
        messages: list[AIMessageInput], system_prompt: str | None
    ) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if system_prompt:
            out.append({"role": "system", "content": system_prompt})
        for msg in messages:
            role = "assistant" if msg.role == "assistant" else "user"
            out.append({"role": role, "content": msg.content})
        return out

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
        target_model = model or "llama3.1"
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": self._to_messages(messages, system_prompt),
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(
                    f"{self._settings.ollama_base_url}/api/chat",
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise AIProviderError("Ollama request timed out.", code="provider_timeout", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("Unable to reach Ollama server.", code="provider_unreachable", status_code=502) from exc

        if response.status_code >= 400:
            raise AIProviderError(
                f"Ollama returned status {response.status_code}.",
                code="provider_error",
                status_code=502,
            )

        data = response.json()
        prompt_tok = int(data.get("prompt_eval_count") or 0)
        comp_tok = int(data.get("eval_count") or 0)
        return AICompletionResponse(
            content=(data.get("message") or {}).get("content") or "",
            provider=self.provider_name,
            model=target_model,
            usage=AIUsage(
                prompt_tokens=prompt_tok,
                completion_tokens=comp_tok,
                total_tokens=prompt_tok + comp_tok,
            ),
            finish_reason="stop",
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
        target_model = model or "llama3.1"
        payload = {
            "model": target_model,
            "messages": self._to_messages(messages, system_prompt),
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{self._settings.ollama_base_url}/api/chat",
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        raise AIProviderError("Ollama streaming error.", code="provider_error", status_code=502)
                    async for raw_line in response.aiter_lines():
                        if not raw_line.strip():
                            continue
                        try:
                            chunk = json.loads(raw_line)
                        except json.JSONDecodeError:
                            continue
                        text = (chunk.get("message") or {}).get("content") or ""
                        if text:
                            yield AIStreamChunk(delta_text=text, done=False)
                        if chunk.get("done"):
                            break
                    yield AIStreamChunk(delta_text="", done=True, usage=AIUsage(), finish_reason="stop")
        except httpx.HTTPError as exc:
            raise AIProviderError("Unable to reach Ollama stream API.", code="provider_unreachable", status_code=502) from exc

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        if not texts:
            return []
        target_model = model or "nomic-embed-text"
        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(
                    f"{self._settings.ollama_base_url}/api/embed",
                    json={"model": target_model, "input": texts},
                )
        except httpx.HTTPError as exc:
            raise AIProviderError("Unable to reach Ollama embed API.", code="provider_unreachable", status_code=502) from exc
        if response.status_code >= 400:
            raise AIProviderError("Ollama embed error.", code="provider_error", status_code=502)
        return response.json().get("embeddings") or []
