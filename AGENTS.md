# Repository Guidelines

## Project Structure & Module Organization

Backend code lives in `app/`. Key areas are `app/api` for FastAPI routes, `app/graph` for LangGraph workflow/state, `app/nodes` for agent nodes, `app/services` for external integrations and persistence, `app/rag` for retrieval helpers, and `app/models` for schemas. Backend tests live in `tests/`. The React frontend lives in `frontend/src`, with components in `frontend/src/components`, hooks in `frontend/src/hooks`, and static assets in `frontend/src/assets` and `frontend/public`. Project documentation is under `docs/`, including plans, diagrams, RAG templates, and whitepapers.

## Build, Test, and Development Commands

Use an isolated Python environment such as Conda `llm_env`.

```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
conda run -n llm_env python -m pytest -q --tb=short
```

Use `pnpm` for frontend work:

```bash
cd frontend
pnpm install
pnpm run dev -- --host 0.0.0.0
pnpm run build
pnpm run lint
node --test
```

If RAGFlow or the local BGE-M3 embedding service is needed, follow `docs/rag/start_command.md` for the Docker and model-server commands instead of duplicating them here.

## Coding Style & Naming Conventions

Use 4-space indentation for Python and keep modules focused by domain. Prefer typed Pydantic models and explicit service boundaries over ad hoc dictionaries for cross-module contracts. React components use PascalCase filenames, hooks use `useX.js`, and helper tests sit beside helpers as `*.test.js`. Keep comments brief and only where they clarify non-obvious behavior.

## Testing Guidelines

Backend tests use `pytest`; name files `test_*.py` and keep fixtures deterministic. Frontend logic tests use Node's built-in `node:test`; name files `*.test.js`. Risk, alert, WebSocket, RAG, and agent-routing changes must include targeted regression coverage or document why existing coverage is sufficient.

## Commit & Pull Request Guidelines

Follow Conventional Commits, for example `feat(alerts): persist high risk alert events` or `docs(git): rewrite rules for github flow`. This repository follows GitHub Flow: branch from `main`, open a PR, pass checks, review, squash merge, then delete the branch. PRs should describe scope, validation commands, risks, and rollback notes. Do not mix unrelated refactors with feature or fix work.

## Security & Configuration Tips

Copy `.env.example` to `.env` locally and never commit secrets, real student data, raw private media, or local environment files. Treat high-risk alerting, data retention, privacy, RAG data, and audit behavior as safety-sensitive changes requiring explicit review.
