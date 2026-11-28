from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class AIChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    conversation_id: int | None = None
    provider: str | None = Field(default=None, max_length=50)
    model: str | None = Field(default=None, max_length=100)


class AIMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: str
    content: str
    provider: str | None = None
    model: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    citations: list[dict[str, Any]] | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int | None = None
    status: str
    created_at: datetime


class AIChatResponse(BaseModel):
    conversation_id: int
    conversation_title: str
    message: AIMessageOut


class AIConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    is_pinned: bool
    is_archived: bool
    provider: str | None = None
    model: str | None = None
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AIConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    is_pinned: bool | None = None
    is_archived: bool | None = None


class AIFeedbackCreate(BaseModel):
    rating: Literal["positive", "negative"]
    comment: str | None = Field(default=None, max_length=1000)


class AIProviderConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: int
    active_provider: str
    active_model: str
    embedding_model: str
    is_enabled: bool
    allow_general_chat: bool
    allow_rag: bool
    allow_tools: bool
    max_tokens_per_request: int
    daily_user_token_limit: int
    temperature: float


class AIProviderConfigUpdate(BaseModel):
    active_provider: str | None = Field(default=None, max_length=50)
    active_model: str | None = Field(default=None, max_length=100)
    embedding_model: str | None = Field(default=None, max_length=100)
    is_enabled: bool | None = None
    allow_general_chat: bool | None = None
    allow_rag: bool | None = None
    allow_tools: bool | None = None
    max_tokens_per_request: int | None = Field(default=None, ge=128, le=8192)
    daily_user_token_limit: int | None = Field(default=None, ge=1000, le=5000000)
    temperature: float | None = Field(default=None, ge=0.0, le=1.5)


class AIDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    filename: str
    content_type: str
    category: str
    visibility: str
    status: str
    chunk_count: int
    file_size_bytes: int
    created_at: datetime
