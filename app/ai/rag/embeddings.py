import math
from app.ai.config import AISettings, get_ai_settings
from app.ai.providers import get_ai_provider
from app.ai.providers.base import AIProviderError


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def generate_embeddings(
    texts: list[str],
    *,
    provider_name: str | None = None,
    embedding_model: str | None = None,
    settings: AISettings | None = None,
) -> list[list[float]] | None:
    """Generate embeddings via the active AI provider when enabled and configured."""
    if not texts:
        return []
    cfg = settings or get_ai_settings()
    target_provider = (provider_name or cfg.default_provider).strip().lower()
    if not cfg.enabled or not cfg.has_provider_credentials(target_provider):
        return None

    try:
        provider = get_ai_provider(target_provider, cfg)
        return await provider.embed(texts, model=embedding_model or cfg.default_embedding_model)
    except AIProviderError:
        return None
