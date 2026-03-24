# Backend Skeleton Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a runnable FastAPI + LangGraph backend skeleton for a multi-agent college mental-health risk screening assistant, with a model-agnostic LLM adapter and a high-risk referral loop.

**Architecture:** The backend is organized into API, graph orchestration, node logic, schemas, and infrastructure services. LangGraph owns state transitions; node functions update a shared typed state; LLM access goes through a custom `LLMClient` interface backed by LiteLLM for Qwen/Bailian today and any OpenAI-compatible or local model later.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, LangGraph, LiteLLM, Uvicorn, Pytest

---

### Task 1: Scaffold project structure and dependencies

**Files:**
- Create: `app/__init__.py`
- Create: `app/api/__init__.py`
- Create: `app/api/routes/__init__.py`
- Create: `app/core/__init__.py`
- Create: `app/graph/__init__.py`
- Create: `app/models/__init__.py`
- Create: `app/nodes/__init__.py`
- Create: `app/services/__init__.py`
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `README.md`

**Step 1: Write the failing test**

Create a smoke test placeholder that imports `app.main`.

```python
def test_app_can_import():
    from app.main import app
    assert app is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_app_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError` for `app.main`

**Step 3: Write minimal implementation**

Create package directories and minimal dependency file with:
- `fastapi`
- `uvicorn`
- `langgraph`
- `litellm`
- `pydantic`
- `python-dotenv`
- `pytest`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_app_smoke.py -v`
Expected: PASS after `app.main` exists

**Step 5: Commit**

```bash
git add app requirements.txt .env.example README.md tests/test_app_smoke.py
git commit -m "feat: scaffold backend project structure"
```

### Task 2: Define shared schemas and typed graph state

**Files:**
- Create: `app/models/schemas.py`
- Create: `app/graph/state.py`
- Test: `tests/test_state_schema.py`

**Step 1: Write the failing test**

```python
from app.graph.state import PsychologyGraphState
from app.models.schemas import ChatRequest

def test_chat_request_supports_engineering_payload():
    payload = ChatRequest(
        session_id="sess-1",
        message="我最近很累",
        multimodal_features={"facial_emotion": "sad"},
        user_profile={"grade": "freshman"},
    )
    assert payload.session_id == "sess-1"
    assert payload.multimodal_features["facial_emotion"] == "sad"

def test_state_type_contains_required_keys():
    required = PsychologyGraphState.__annotations__
    assert "chat_history" in required
    assert "multimodal_features" in required
    assert "current_risk_score" in required
    assert "agent_judgments" in required
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_state_schema.py -v`
Expected: FAIL because state and schemas do not exist

**Step 3: Write minimal implementation**

Define:
- `ChatRequest`
- `ChatResponse`
- `CounselorAlertPayload`
- `PsychologyGraphState` as `TypedDict`
- Supporting `RiskLevel` literal/enum and message item schemas

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_state_schema.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/models/schemas.py app/graph/state.py tests/test_state_schema.py
git commit -m "feat: add request schemas and graph state"
```

### Task 3: Add model abstraction and configuration layer

**Files:**
- Create: `app/core/config.py`
- Create: `app/services/llm_client.py`
- Test: `tests/test_llm_client_config.py`

**Step 1: Write the failing test**

```python
from app.core.config import get_settings

def test_settings_expose_model_provider_defaults():
    settings = get_settings()
    assert settings.llm_provider in {"litellm"}
    assert settings.llm_model
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_client_config.py -v`
Expected: FAIL because settings module does not exist

**Step 3: Write minimal implementation**

Implement:
- `Settings` via Pydantic
- Environment variables for Bailian/Qwen access
- `BaseLLMClient` protocol or abstract class
- `LiteLLMClient` implementation with a `complete_json(...)` helper

Node code should depend only on `BaseLLMClient`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_llm_client_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/core/config.py app/services/llm_client.py tests/test_llm_client_config.py
git commit -m "feat: add model abstraction layer"
```

### Task 4: Implement alert adapter and response helper

**Files:**
- Create: `app/services/alert_service.py`
- Test: `tests/test_alert_service.py`

**Step 1: Write the failing test**

```python
from app.services.alert_service import MockAlertService

def test_mock_alert_service_returns_success_result():
    service = MockAlertService()
    result = service.send_high_risk_alert({"session_id": "sess-1"})
    assert result["sent"] is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_alert_service.py -v`
Expected: FAIL because alert service does not exist

**Step 3: Write minimal implementation**

Implement a simple adapter that:
- exposes `send_high_risk_alert(payload: dict) -> dict`
- returns a mock webhook response
- can later be swapped with a real HTTP webhook implementation

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_alert_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/alert_service.py tests/test_alert_service.py
git commit -m "feat: add mock high-risk alert service"
```

### Task 5: Implement the three LangGraph node skeletons

**Files:**
- Create: `app/nodes/information_extractor.py`
- Create: `app/nodes/risk_assessor.py`
- Create: `app/nodes/response_generator.py`
- Test: `tests/test_nodes.py`

**Step 1: Write the failing test**

```python
from app.nodes.information_extractor import information_extractor_node
from app.nodes.risk_assessor import risk_assessor_node
from app.nodes.response_generator import response_generator_node

def test_risk_assessor_flags_high_risk_keywords():
    state = {
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "我不想活了"}],
        "multimodal_features": {},
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {"emotion_keywords": ["不想活了"]},
        "risk_level": "low",
        "referral_required": False,
    }
    updated = risk_assessor_node(state)
    assert updated["risk_level"] == "high"
    assert updated["referral_required"] is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_nodes.py -v`
Expected: FAIL because node modules do not exist

**Step 3: Write minimal implementation**

Implement node skeletons with detailed comments:
- `information_extractor_node`: gather latest user text + multimodal tags, call `BaseLLMClient`, parse emotion keywords, update `agent_judgments`
- `risk_assessor_node`: combine LLM judgment with a rule-based high-risk keyword fallback
- `response_generator_node`: generate supportive reply; when high risk, force `referral_required=True` and attach hotline card payload

Use pseudo-production logic where external LLM failures fall back to deterministic safe defaults.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_nodes.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/nodes tests/test_nodes.py
git commit -m "feat: add multi-agent node skeletons"
```

### Task 6: Build and compile the LangGraph workflow

**Files:**
- Create: `app/graph/workflow.py`
- Test: `tests/test_workflow.py`

**Step 1: Write the failing test**

```python
from app.graph.workflow import build_graph

def test_graph_compiles_successfully():
    graph = build_graph()
    assert graph is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_workflow.py -v`
Expected: FAIL because workflow builder does not exist

**Step 3: Write minimal implementation**

Implement a `build_graph()` function that:
- creates a `StateGraph(PsychologyGraphState)`
- adds the three nodes
- wires `START -> information_extractor -> risk_assessor -> response_generator -> END`
- returns the compiled graph

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_workflow.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/graph/workflow.py tests/test_workflow.py
git commit -m "feat: compile langgraph workflow"
```

### Task 7: Expose the `/chat` FastAPI endpoint

**Files:**
- Create: `app/api/routes/chat.py`
- Create: `app/main.py`
- Test: `tests/test_chat_api.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient
from app.main import app

def test_chat_endpoint_returns_structured_response():
    client = TestClient(app)
    response = client.post(
        "/chat",
        json={
            "session_id": "sess-1",
            "message": "最近压力很大，睡不着",
            "multimodal_features": {"facial_emotion": "sad"},
            "user_profile": {"school": "demo-university"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "reply" in body
    assert "risk_level" in body
    assert "trace_id" in body
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_chat_api.py -v`
Expected: FAIL because endpoint does not exist

**Step 3: Write minimal implementation**

Implement:
- request parsing
- initial graph state assembly
- compiled graph invocation
- response schema conversion
- startup-safe app creation

Return an engineering-friendly payload with:
- `reply`
- `risk_level`
- `referral_required`
- `agent_judgments`
- `extracted_signals`
- `trace_id`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_chat_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/api/routes/chat.py app/main.py tests/test_chat_api.py
git commit -m "feat: add chat api endpoint"
```

### Task 8: Add integration verification and usage docs

**Files:**
- Modify: `README.md`
- Create: `tests/test_graph_integration.py`

**Step 1: Write the failing test**

```python
from app.graph.workflow import build_graph

def test_full_graph_run_returns_reply():
    graph = build_graph()
    result = graph.invoke({
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "我最近很痛苦"}],
        "multimodal_features": {"facial_emotion": "sad"},
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {},
        "risk_level": "low",
        "referral_required": False,
        "reply": "",
        "trace_id": "trace-1",
        "user_profile": {},
        "alert_status": {},
    })
    assert result["reply"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_graph_integration.py -v`
Expected: FAIL until node outputs and workflow wiring are complete

**Step 3: Write minimal implementation**

Document:
- environment variables
- how to run `uvicorn app.main:app --reload`
- example `/chat` request payload
- where to replace mock alert and model backend later

**Step 4: Run test to verify it passes**

Run: `pytest -q`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md tests/test_graph_integration.py
git commit -m "docs: add backend usage and verification notes"
```
