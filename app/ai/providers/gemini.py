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


class GeminiProvider(AIProviderBase):
    """Google Gemini REST + SSE adapter using httpx with server-side API key."""

    provider_name = "gemini"

    def __init__(self, settings: AISettings) -> None:
        self._settings = settings

    def _require_api_key(self) -> str:
        if not self._settings.gemini_api_key:
            raise AIProviderError(
                "Gemini API key is not configured on the backend.",
                code="missing_api_key",
                status_code=503,
            )
        return self._settings.gemini_api_key

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self._require_api_key(),
        }

    @staticmethod
    def _to_gemini_contents(messages: list[AIMessageInput]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "system":
                continue
            if msg.role == "tool":
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": msg.tool_name or "tool",
                                    "response": {"result": msg.content},
                                }
                            }
                        ],
                    }
                )
                continue
            role = "model" if msg.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg.content}]})
        return contents

    @staticmethod
    def _to_gemini_tools(tools: list[AIToolDefinition] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [
            {
                "functionDeclarations": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }
                    for t in tools
                ]
            }
        ]

    def _build_payload(
        self,
        messages: list[AIMessageInput],
        *,
        system_prompt: str | None,
        tools: list[AIToolDefinition] | None,
        temperature: float,
        max_tokens: int,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if response_schema is not None:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = response_schema

        payload: dict[str, Any] = {
            "contents": self._to_gemini_contents(messages),
            "generationConfig": generation_config,
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        gemini_tools = self._to_gemini_tools(tools)
        if gemini_tools:
            payload["tools"] = gemini_tools
        return payload

    @staticmethod
    def _parse_parts(candidate: dict[str, Any]) -> tuple[str, list[AIToolCall]]:
        text_chunks: list[str] = []
        tool_calls: list[AIToolCall] = []
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            if "text" in part and part["text"] is not None:
                text_chunks.append(part["text"])
            if "functionCall" in part and part["functionCall"]:
                fc = part["functionCall"]
                tool_calls.append(
                    AIToolCall(
                        name=fc.get("name", ""),
                        arguments=fc.get("args") or {},
                    )
                )
        return "".join(text_chunks), tool_calls

    @staticmethod
    def _parse_usage(data: dict[str, Any]) -> AIUsage:
        meta = data.get("usageMetadata") or {}
        prompt_tokens = int(meta.get("promptTokenCount") or 0)
        completion_tokens = int(meta.get("candidatesTokenCount") or 0)
        total_tokens = int(meta.get("totalTokenCount") or (prompt_tokens + completion_tokens))
        return AIUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        code = "provider_error"
        if response.status_code in (401, 403):
            code = "provider_auth_error"
        elif response.status_code == 429:
            code = "provider_rate_limited"
        elif response.status_code == 400:
            code = "provider_bad_request"
        try:
            detail = response.json().get("error", {}).get("message")
        except Exception:
            detail = None
        raise AIProviderError(
            detail or f"Gemini API returned status {response.status_code}.",
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
        target_model = model or self._settings.default_model
        url = f"{self._settings.gemini_base_url}/models/{target_model}:generateContent"
        payload = self._build_payload(
            messages,
            system_prompt=system_prompt,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            response_schema=response_schema,
        )

        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
        except httpx.TimeoutException as exc:
            raise AIProviderError("Gemini request timed out.", code="provider_timeout", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("Unable to reach Gemini API.", code="provider_unreachable", status_code=502) from exc

        self._raise_for_status(response)
        data = response.json()
        candidates = data.get("candidates") or []
        first = candidates[0] if candidates else {}
        text, tool_calls = self._parse_parts(first)
        usage = self._parse_usage(data)

        structured_data = None
        if response_schema is not None and text.strip():
            try:
                structured_data = json.loads(text)
            except json.JSONDecodeError:
                structured_data = None

        return AICompletionResponse(
            content=text,
            provider=self.provider_name,
            model=target_model,
            usage=usage,
            tool_calls=tool_calls,
            finish_reason=first.get("finishReason"),
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
        target_model = model or self._settings.default_model
        url = f"{self._settings.gemini_base_url}/models/{target_model}:streamGenerateContent?alt=sse"
        payload = self._build_payload(
            messages,
            system_prompt=system_prompt,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                async with client.stream("POST", url, headers=self._headers(), json=payload) as response:
                    self._raise_for_status(response)
                    last_usage: AIUsage | None = None
                    last_finish: str | None = None
                    async for raw_line in response.aiter_lines():
                        line = raw_line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        raw_json = line[5:].strip()
                        if not raw_json or raw_json == "[DONE]":
                            continue
                        try:
                            chunk_data = json.loads(raw_json)
                        except json.JSONDecodeError:
                            continue

                        candidates = chunk_data.get("candidates") or []
                        first = candidates[0] if candidates else {}
                        delta_text, tool_calls = self._parse_parts(first)
                        if chunk_data.get("usageMetadata"):
                            last_usage = self._parse_usage(chunk_data)
                        if first.get("finishReason"):
                            last_finish = first.get("finishReason")

                        if delta_text or tool_calls:
                            yield AIStreamChunk(
                                delta_text=delta_text,
                                done=False,
                                tool_calls=tool_calls,
                                usage=last_usage,
                                finish_reason=last_finish,
                            )

                    yield AIStreamChunk(
                        delta_text="",
                        done=True,
                        usage=last_usage or AIUsage(),
                        finish_reason=last_finish or "STOP",
                    )
        except httpx.TimeoutException as exc:
            raise AIProviderError("Gemini stream timed out.", code="provider_timeout", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("Unable to reach Gemini streaming API.", code="provider_unreachable", status_code=502) from exc

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []
        target_model = model or self._settings.default_embedding_model
        url = f"{self._settings.gemini_base_url}/models/{target_model}:batchEmbedContents"
        payload = {
            "requests": [
                {
                    "model": f"models/{target_model}",
                    "content": {"parts": [{"text": text}]},
                }
                for text in texts
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
        except httpx.TimeoutException as exc:
            raise AIProviderError("Gemini embedding timed out.", code="provider_timeout", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("Unable to reach Gemini embedding API.", code="provider_unreachable", status_code=502) from exc

        self._raise_for_status(response)
        data = response.json()
        return [item.get("values") or [] for item in (data.get("embeddings") or [])]
