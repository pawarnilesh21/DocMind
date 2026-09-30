import math

from app.config import settings
from app.services.provider import ProviderError, post_json

DIMENSIONS = 768


def generate_embeddings(texts: list[str], *, query: bool = False) -> list[list[float]]:
    if not texts:
        return []
    if not settings.GEMINI_API_KEY:
        raise ProviderError("Embedding provider is not configured")
    model = settings.EMBEDDING_MODEL
    vectors = []
    for offset in range(0, len(texts), 32):
        batch = texts[offset : offset + 32]
        response = post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents",
            headers={"x-goog-api-key": settings.GEMINI_API_KEY},
            payload={
                "requests": [
                    {
                        "model": f"models/{model}",
                        "content": {"parts": [{"text": text}]},
                        "taskType": "RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT",
                        "outputDimensionality": DIMENSIONS,
                    }
                    for text in batch
                ]
            },
        )
        embeddings = response.get("embeddings", [])
        if len(embeddings) != len(batch):
            raise ProviderError("Embedding count mismatch")
        for item in embeddings:
            values = item.get("values", [])
            if len(values) != DIMENSIONS or not all(
                isinstance(v, (int, float)) and math.isfinite(v) for v in values
            ):
                raise ProviderError("Invalid embedding dimensions or values")
            norm = math.sqrt(sum(v * v for v in values))
            if norm == 0:
                raise ProviderError("Invalid zero embedding")
            vectors.append([v / norm for v in values])
    return vectors
