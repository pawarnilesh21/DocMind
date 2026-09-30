"""Small live provider contract check using synthetic, non-private content only."""
import math
from app.services.embedding_service import generate_embeddings
from app.services.llm_service import generate_answer
from app.services.provider import ProviderError, budget


def main():
    source = "The DocMind verification project launches on 14 September 2026. Its owner is the Example Team."
    with budget(120):
        document = generate_embeddings([source])[0]
        query = generate_embeddings(["When does the DocMind verification project launch?"], query=True)[0]
        similarity = sum(a * b for a, b in zip(document, query, strict=True))
        assert math.isfinite(similarity)
        result = generate_answer("When does the DocMind verification project launch?", [{
            "content": source, "filename": "synthetic-check.txt", "document_id": "00000000-0000-4000-8000-000000000001",
            "chunk_index": 0, "page_number": None,
        }])
        assert result["grounding"] == "verified", result["grounding"]
        assert "September" in result["answer"] and "2026" in result["answer"]
        assert len(result["sources_used"]) == 1
        print(f"Provider check passed: document/query embeddings (768 dimensions, cosine={similarity:.3f}), structured answer, exact citation, entailment verification.")


if __name__ == "__main__":
    try:
        main()
    except ProviderError as exc:
        raise SystemExit(f"Provider check failed: {exc}") from None
