from app.ai.config import AISettings, get_ai_settings
from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.base import AIProviderBase, AIProviderError
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.openai_compat import OpenAICompatibleProvider

SUPPORTED_PROVIDERS: dict[str, dict[str, object]] = {
    "gemini": {
        "label": "Google Gemini",
        "implemented": True,
        "default_model": "gemini-3.0-flash",
        "models": ["gemini-3.0-flash", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
        "embedding_models": ["text-embedding-004"],
    },
    "openai": {
        "label": "OpenAI",
        "implemented": True,
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "gpt-4o"],
        "embedding_models": ["text-embedding-3-small"],
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "implemented": True,
        "default_model": "claude-3-5-sonnet-latest",
        "models": ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"],
    },
    "groq": {
        "label": "Groq",
        "implemented": True,
        "default_model": "llama-3.3-70b-versatile",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    },
    "deepseek": {
        "label": "DeepSeek",
        "implemented": True,
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "ollama": {
        "label": "Ollama (Local)",
        "implemented": True,
        "default_model": "llama3.1",
        "models": ["llama3.1", "qwen2.5"],
        "embedding_models": ["nomic-embed-text"],
    },
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
    if name == "openai":
        return OpenAICompatibleProvider(
            cfg,
            provider_name="openai",
            base_url="https://api.openai.com/v1",
            api_key=cfg.openai_api_key,
            default_model="gpt-4o-mini",
            supports_embeddings=True,
        )
    if name == "groq":
        return OpenAICompatibleProvider(
            cfg,
            provider_name="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key=cfg.groq_api_key,
            default_model="llama-3.3-70b-versatile",
        )
    if name == "deepseek":
        return OpenAICompatibleProvider(
            cfg,
            provider_name="deepseek",
            base_url="https://api.deepseek.com/v1",
            api_key=cfg.deepseek_api_key,
            default_model="deepseek-chat",
        )
    if name == "anthropic":
        return AnthropicProvider(cfg)
    if name == "ollama":
        return OllamaProvider(cfg)

    raise AIProviderError(
        f"Unsupported AI provider '{name}'.",
        code="unsupported_provider",
        status_code=400,
    )
