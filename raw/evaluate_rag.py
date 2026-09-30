"""Evaluate a user's ready documents without hiding failed or empty-retrieval cases.

Usage: python -m raw.evaluate_rag --email you@example.com --document-id UUID --cases evaluation/cases.json
Each case: {"id":"case-1","question":"...","answerable":true,"expected_terms":["..."]}
Runs paid provider requests and writes aggregate metrics only unless --output is specified.
"""

import argparse
import json
import uuid
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import User
from app.services.llm_service import generate_answer
from app.services.provider import budget
from app.services.retrieval_service import retrieve


class Case(BaseModel):
    id: str
    question: str = Field(min_length=1, max_length=4000)
    answerable: bool
    expected_terms: list[str] = Field(default_factory=list)


def evaluate(cases, owner_id, document_ids):
    results = []
    for case in cases:
        row = {"id": case.id, "retrieved": False, "passed": False, "grounding": "error"}
        try:
            with budget(120), SessionLocal() as db:
                chunks = retrieve(db, case.question, owner_id=owner_id, document_ids=document_ids)
                db.commit()
                row["retrieved"] = bool(chunks)
                answer = generate_answer(case.question, chunks)
                row["grounding"] = answer["grounding"]
                if case.answerable:
                    row["passed"] = (
                        bool(chunks)
                        and bool(answer["sources_used"])
                        and answer["grounding"] == "verified"
                        and all(
                            term.casefold() in answer["answer"].casefold() for term in case.expected_terms
                        )
                    )
                else:
                    row["passed"] = (
                        answer["grounding"] in {"abstained", "rejected"} and not answer["sources_used"]
                    )
        except Exception as exc:
            row["error_type"] = type(exc).__name__
        # Every case remains in the denominator, including exceptions and empty retrieval.
        results.append(row)
    return {
        "cases": len(results),
        "passed": sum(r["passed"] for r in results),
        "pass_rate": sum(r["passed"] for r in results) / len(results) if results else 0,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--document-id", action="append", type=uuid.UUID, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--minimum-pass-rate", type=float, default=0.8)
    args = parser.parse_args()
    if not 0 <= args.minimum_pass_rate <= 1:
        raise SystemExit("minimum-pass-rate must be between 0 and 1")
    cases = [Case.model_validate(case) for case in json.loads(args.cases.read_text(encoding="utf-8"))]
    if not 1 <= len(cases) <= 20:
        raise SystemExit("Provide between 1 and 20 cases per evaluation")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email.lower(), User.active.is_(True)))
        if not user:
            raise SystemExit("Active account not found")
        owner_id = user.id
    report = evaluate(cases, owner_id, args.document_id)
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if report["pass_rate"] < args.minimum_pass_rate:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
