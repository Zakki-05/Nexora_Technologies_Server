from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


class AIProviderError(Exception):
    """Normalized exception raised by LLM provider adapters."""

    def __init__(self, message: str, *, code: str = "provider_error", status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


@dataclass
class AIMessageInput:
    """Provider-neutral chat message."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_name: str | None = None
    tool_call_id: str | None = None


@dataclass
class AIToolDefinition:
    """Provider-neutral tool/function declaration."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class AIToolCall:
    """Normalized tool invocation requested by an LLM."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None


@dataclass
class AIUsage:
    """Normalized token accounting."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class AICompletionResponse:
    """Normalized non-streaming LLM response."""

    content: str
    provider: str
    model: str
    usage: AIUsage = field(default_factory=AIUsage)
    tool_calls: list[AIToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    structured_data: dict[str, Any] | None = None


@dataclass
class AIStreamChunk:
    """Normalized streaming delta or terminal chunk."""

    delta_text: str = ""
    done: bool = False
    tool_calls: list[AIToolCall] = field(default_factory=list)
    usage: AIUsage | None = None
    finish_reason: str | None = None


class AIProviderBase(ABC):
    """Common interface implemented by all Nexora AI LLM provider adapters."""

    provider_name: str = "base"

    @abstractmethod
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
        """Execute a single chat/tool completion."""

    @abstractmethod
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
        """Stream completion chunks as an async iterator."""

    @abstractmethod
    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """Generate vector embeddings for one or more text chunks."""
