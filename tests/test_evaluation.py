from unittest.mock import Mock

from raw import evaluate_rag


def test_empty_retrieval_and_provider_failure_remain_in_denominator(monkeypatch):
    cases = [
        evaluate_rag.Case(id="empty", question="What?", answerable=True, expected_terms=["answer"]),
        evaluate_rag.Case(id="error", question="What else?", answerable=True, expected_terms=["answer"]),
    ]
    monkeypatch.setattr(evaluate_rag, "retrieve", Mock(side_effect=[[], RuntimeError("unavailable")]))
    monkeypatch.setattr(
        evaluate_rag,
        "generate_answer",
        Mock(return_value={"answer": "No information", "grounding": "abstained", "sources_used": []}),
    )
    result = evaluate_rag.evaluate(cases, None, [])
    assert result["cases"] == 2
    assert result["passed"] == 0
    assert len(result["results"]) == 2
