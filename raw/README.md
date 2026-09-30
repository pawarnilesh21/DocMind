# Optional tooling and local development archive

The application does not import this folder during normal operation.

The following files remain in GitHub because they support reproducibility:

- `evaluate_rag.py`: optional RAG evaluation command, imported by `tests/test_evaluation.py`.
- `PRODUCTION_READINESS.md`: dated verification results and outstanding release checks.
- `__init__.py`: makes the evaluator importable.
- This README.

Other files in this directory are local-only historical experiments and notes, excluded by the root `.gitignore`. Some describe obsolete ChromaDB/LangChain code or call paid providers. They are retained for reference, not supported startup commands. Use `SHARING_GUIDE.md` and the root README for the current application.

From the project root, with the local Python environment installed:

```powershell
.\.venv-prod\Scripts\python.exe -m raw.evaluate_rag --help
```

An evaluation requires an existing user's ready documents and a JSON case file; it sends document excerpts to the configured AI providers and can incur API charges. Private case files and report directories under `evaluation/` are ignored; only `cases.example.json` is published.

The automated test directories `tests/` and `frontend/tests/` remain in the repository. They are not the old root-level `test_*.py` experiments archived here.
