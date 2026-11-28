from app.ai.config import AISettings, get_ai_settings
from app.ai.providers.base import AIProviderBase, AIProviderError
from app.ai.providers.gemini import GeminiProvider

SUPPORTED_PROVIDERS: dict[str, dict[str, object]] = {
    "gemini": {
        "label": "Google Gemini",
        "implemented": True,
        "default_model": "gemini-2.5-flash",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
        "embedding_models": ["text-embedding-004"],
    },
    "openai": {"label": "OpenAI", "implemented": False, "default_model": "gpt-4o-mini"},
    "anthropic": {"label": "Anthropic Claude", "implemented": False, "default_model": "claude-3-5-sonnet-latest"},
    "groq": {"label": "Groq", "implemented": False, "default_model": "llama-3.3-70b-versatile"},
    "deepseek": {"label": "DeepSeek", "implemented": False, "default_model": "deepseek-chat"},
    "ollama": {"label": "Ollama (Local)", "implemented": False, "default_model": "llama3.1"},
}


def get_ai_provider(
    provider_name: str | None = None,
    settings: AISettings | None = None,
) -> AIProviderBase:
    """Resolve and instantiate an AI provider adapter by name."""
    cfg = settings or get_ai_settings()
    name = (provider_name or cfg.default_provider).strip().lower()
    if name == "gemini":
        return GeminiProvider(cfg)
    if name in SUPPORTED_PROVIDERS:
        raise AIProviderError(
            f"Provider '{name}' is registered in the catalog but not yet activated.",
            code="provider_not_implemented",
            status_code=501,
        )
    raise AIProviderError(
        f"Unsupported AI provider '{name}'.",
        code="unsupported_provider",
        status_code=400,
    )
