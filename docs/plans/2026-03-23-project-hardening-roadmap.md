# Project Hardening And Pilot Readiness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将当前多智能体心理风险辅助原型，推进到可做校内试点验证的工程化版本。

**Architecture:** 先冻结产品契约和安全边界，再补足持久化、观测、前端自动化测试、CI/CD 和部署基建，最后再做更重的模型升级和多模态扩展。顺序上优先做“让系统可信、可测、可回放、可部署”，而不是继续叠加新模型和新模态。

**Tech Stack:** FastAPI, LangGraph, LiteLLM, WebSocket, React, Vite, Tailwind CSS, Pytest, Node test, PostgreSQL/Redis, GitHub Actions, Docker

---

### Task 1: Freeze MVP Contract And Documentation

**Files:**
- Modify: `README.md`
- Modify: `app/models/schemas.py`
- Modify: `app/core/config.py`
- Create: `docs/pilot-mvp.md`

**Step 1: Write the failing test**

Add or update a config/schema test to lock the current public contract and required env behavior.

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env python -m pytest -q tests/test_state_schema.py tests/test_llm_client_config.py`
Expected: FAIL if new required contract/config fields are not implemented yet.

**Step 3: Write minimal implementation**

Do the following:
- Define pilot-scope input/output contract in `docs/pilot-mvp.md`
- Align `README.md` with current reality
- Update test-count wording in docs
- Promote configuration from lightweight dataclass assumptions to a clearly documented pilot contract

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env python -m pytest -q tests/test_state_schema.py tests/test_llm_client_config.py`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md app/models/schemas.py app/core/config.py docs/pilot-mvp.md
git commit -m "docs: freeze pilot mvp contract"
```

### Task 2: Replace In-Memory Session State With Persistent Checkpointing

**Files:**
- Modify: `app/graph/workflow.py`
- Modify: `app/core/config.py`
- Create: `app/services/checkpoint_store.py`
- Create: `tests/test_checkpoint_store.py`

**Step 1: Write the failing test**

Add a test showing that the same `session_id` can resume state after process boundary or recreated graph instance.

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env python -m pytest -q tests/test_checkpoint_store.py`
Expected: FAIL because current graph uses `MemorySaver()`.

**Step 3: Write minimal implementation**

Do the following:
- Abstract checkpointer creation into `app/services/checkpoint_store.py`
- Keep development fallback, but support Redis/PostgreSQL-backed persistence for pilot/staging
- Make backend startup fail fast when pilot environment requires persistence but is misconfigured

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env python -m pytest -q tests/test_checkpoint_store.py tests/test_workflow.py tests/test_graph_integration.py`
Expected: PASS

**Step 5: Commit**

```bash
git add app/graph/workflow.py app/core/config.py app/services/checkpoint_store.py tests/test_checkpoint_store.py
git commit -m "feat: add persistent graph checkpointing"
```

### Task 3: Add Safety Evaluation, Masked Audit Logging, And Alert Reliability

**Files:**
- Modify: `app/services/alert_service.py`
- Modify: `app/services/trace_service.py`
- Modify: `app/api/routes/chat.py`
- Modify: `app/api/routes/ws_chat.py`
- Create: `app/services/audit_log_service.py`
- Create: `tests/test_audit_log_service.py`
- Create: `tests/test_safety_eval_contract.py`

**Step 1: Write the failing test**

Add tests that prove:
- sensitive raw user text is masked in logs/traces
- high-risk routing always reaches referral flow
- webhook retries/backoff/dead-letter behavior is deterministic

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env python -m pytest -q tests/test_alert_service.py tests/test_audit_log_service.py tests/test_safety_eval_contract.py`
Expected: FAIL because masked audit logging and formal safety eval contract do not yet exist.

**Step 3: Write minimal implementation**

Do the following:
- centralize masked audit logging
- define a small offline safety evaluation set for low/medium/high examples
- add reliable async alert delivery semantics and explicit failure statuses

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env python -m pytest -q tests/test_alert_service.py tests/test_audit_log_service.py tests/test_safety_eval_contract.py tests/test_nodes.py tests/test_ws_chat.py`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/alert_service.py app/services/trace_service.py app/api/routes/chat.py app/api/routes/ws_chat.py app/services/audit_log_service.py tests/test_audit_log_service.py tests/test_safety_eval_contract.py
git commit -m "feat: add masked audit logging and safety evaluation"
```

### Task 4: Add Frontend Automated Testing And End-To-End Realtime Coverage

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/ChatInterface.test.jsx`
- Create: `frontend/src/hooks/useAudioStream.test.js`
- Create: `frontend/vitest.config.js`
- Create: `frontend/test/setup.js`
- Create: `tests/test_realtime_e2e.py`

**Step 1: Write the failing test**

Add frontend tests that prove:
- stage copy renders
- assistant typewriter playback grows over time
- support card renders only on referral responses

Add a backend/browser-integrated realtime smoke test if feasible.

**Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test`
Expected: FAIL because frontend test runner is not configured.

**Step 3: Write minimal implementation**

Do the following:
- add `vitest` and React Testing Library
- cover the text chat happy path and degraded path
- add CI-friendly frontend test command

**Step 4: Run test to verify it passes**

Run: `npm --prefix frontend test -- --run`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/package.json frontend/vitest.config.js frontend/test/setup.js frontend/src/ChatInterface.test.jsx frontend/src/hooks/useAudioStream.test.js tests/test_realtime_e2e.py
git commit -m "test: add frontend realtime coverage"
```

### Task 5: Add CI, Containerization, And One-Command Local Environments

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `Makefile`
- Modify: `README.md`

**Step 1: Write the failing test**

Treat CI config itself as the verification target by ensuring all required commands exist and run locally first.

**Step 2: Run verification locally**

Run:
- `conda run -n llm_env python -m pytest -q --tb=short`
- `npm --prefix frontend run build`
- `npm --prefix frontend test -- --run`

Expected: all local checks pass before encoding them into CI.

**Step 3: Write minimal implementation**

Do the following:
- build backend image
- build frontend production asset image or static-serving stage
- add CI for backend tests, frontend tests, and frontend build
- add `make test`, `make dev`, `make up`

**Step 4: Run test to verify it passes**

Run: `docker compose config`
Expected: PASS and CI yaml references only existing commands.

**Step 5: Commit**

```bash
git add .github/workflows/ci.yml Dockerfile docker-compose.yml Makefile README.md
git commit -m "chore: add ci and containerized dev workflow"
```

### Task 6: Prepare Pilot Deployment And Staging Acceptance

**Files:**
- Create: `docs/staging-checklist.md`
- Create: `docs/runbooks/high-risk-alert-runbook.md`
- Create: `docs/runbooks/service-degradation-runbook.md`
- Modify: `README.md`

**Step 1: Write the failing test**

No code-first test required; create explicit acceptance checklist with measurable gates.

**Step 2: Run verification**

Run the full project validation:
- `conda run -n llm_env python -m pytest -q --tb=short`
- `npm --prefix frontend test -- --run`
- `npm --prefix frontend run build`

Expected: all green before staging promotion.

**Step 3: Write minimal implementation**

Document:
- staging env variables
- rollback path
- alert escalation flow
- on-call/operator responsibilities
- privacy/data-retention boundaries

**Step 4: Validate checklist**

Expected:
- pilot operator can start services
- operator can identify high-risk alert path
- operator can explain what is logged, masked, retained, and deleted

**Step 5: Commit**

```bash
git add docs/staging-checklist.md docs/runbooks/high-risk-alert-runbook.md docs/runbooks/service-degradation-runbook.md README.md
git commit -m "docs: add staging and pilot runbooks"
```

### Task 7: Only After The Above, Upgrade Models And Deep Multimodal Capabilities

**Files:**
- Modify: `app/services/llm_client.py`
- Modify: `app/nodes/voice_analyzer.py`
- Modify: `app/nodes/face_analyzer.py`
- Create: `app/services/ser_model_service.py`
- Create: `tests/test_ser_model_service.py`

**Step 1: Write the failing test**

Add deterministic tests around model adapter contracts and failure fallback behavior.

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env python -m pytest -q tests/test_ser_model_service.py tests/test_llm_client.py`
Expected: FAIL because deep model services are not yet implemented.

**Step 3: Write minimal implementation**

Do the following:
- add local-model adapter for A40 deployment
- add deep SER inference behind a safe feature flag
- keep rule fallback and referral guarantees intact

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env python -m pytest -q tests/test_ser_model_service.py tests/test_llm_client.py tests/test_nodes.py tests/test_graph_integration.py`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/llm_client.py app/nodes/voice_analyzer.py app/nodes/face_analyzer.py app/services/ser_model_service.py tests/test_ser_model_service.py
git commit -m "feat: add local model and deep multimodal adapters"
```
