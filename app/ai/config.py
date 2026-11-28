import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class AISettings:
    """Backend-only AI configuration loaded from environment variables."""

    enabled: bool
    default_provider: str
    default_model: str
    default_embedding_model: str
    request_timeout_seconds: float
    max_tokens_per_request: int
    daily_user_token_limit: int
    max_context_messages: int
    temperature: float
    gemini_api_key: str | None
    gemini_base_url: str
    openai_api_key: str | None
    anthropic_api_key: str | None
    groq_api_key: str | None
    deepseek_api_key: str | None
    ollama_base_url: str

    def has_provider_credentials(self, provider: str) -> bool:
        """Return True when the requested provider has server-side credentials configured."""
        key_map = {
            "gemini": bool(self.gemini_api_key),
            "openai": bool(self.openai_api_key),
            "anthropic": bool(self.anthropic_api_key),
            "groq": bool(self.groq_api_key),
            "deepseek": bool(self.deepseek_api_key),
            "ollama": bool(self.ollama_base_url),
        }
        return key_map.get(provider.lower(), False)


def get_ai_settings() -> AISettings:
    """Load fresh AI settings from the current process environment."""
    return AISettings(
        enabled=_env_bool("AI_ENABLED", False),
        default_provider=os.getenv("AI_DEFAULT_PROVIDER", "gemini").strip().lower(),
        default_model=os.getenv("AI_DEFAULT_MODEL", "gemini-3.0-flash").strip(),
        default_embedding_model=os.getenv("AI_EMBEDDING_MODEL", "text-embedding-004").strip(),
        request_timeout_seconds=_env_float("AI_REQUEST_TIMEOUT_SECONDS", 30.0),
        max_tokens_per_request=_env_int("AI_MAX_TOKENS_PER_REQUEST", 2048),
        daily_user_token_limit=_env_int("AI_DAILY_USER_TOKEN_LIMIT", 50000),
        max_context_messages=_env_int("AI_MAX_CONTEXT_MESSAGES", 20),
        temperature=_env_float("AI_TEMPERATURE", 0.3),
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_base_url=os.getenv(
            "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
        ).rstrip("/"),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or None,
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
    )
