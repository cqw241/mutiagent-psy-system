# Task 3 Realtime And UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a WebSocket chat channel with stage events and final token streaming, trigger non-blocking high-risk webhooks, and scaffold a React + Tailwind frontend with a warm chat interface.

**Architecture:** The backend will use LangGraph `astream(..., stream_mode=["updates", "custom"])` to separate stage events from token chunks. The frontend will connect over WebSocket, render soft status transitions, stream assistant text into the chat log, and show a warm referral card when the backend marks a message as high risk.

**Tech Stack:** Python 3.11+, FastAPI, LangGraph, LiteLLM, httpx, React, Vite, Tailwind CSS

---

### Task 1: Define WebSocket event schema and streaming tests

**Files:**
- Modify: `app/models/schemas.py`
- Create: `tests/test_ws_chat.py`

**Step 1: Write the failing test**

Add a websocket test that expects:
- a `stage` event
- one or more `token` events
- a `final` event
- an `end` event

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env pytest tests/test_ws_chat.py -v`
Expected: FAIL because websocket route does not exist

**Step 3: Write minimal implementation**

Add helper schemas/constants for websocket event names if useful.

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env pytest tests/test_ws_chat.py -v`
Expected: PASS

### Task 2: Extend LLM client for streaming output

**Files:**
- Modify: `app/services/llm_client.py`
- Test: `tests/test_response_streaming.py`

**Step 1: Write the failing test**

Add a test for a dummy streaming client consumed by `response_generator_node`.

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env pytest tests/test_response_streaming.py -v`
Expected: FAIL because client has no streaming API

**Step 3: Write minimal implementation**

Introduce an async text streaming method in the abstract client and implement it for LiteLLM.

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env pytest tests/test_response_streaming.py -v`
Expected: PASS

### Task 3: Add async webhook service and safe high-risk handling

**Files:**
- Modify: `app/services/alert_service.py`
- Modify: `app/nodes/response_generator.py`
- Test: `tests/test_nodes.py`

**Step 1: Write the failing test**

Add a test asserting high-risk handling does not block and produces a masked webhook payload.

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env pytest tests/test_nodes.py -v`
Expected: FAIL because async webhook path does not exist

**Step 3: Write minimal implementation**

Add an async webhook sender and fire it with `asyncio.create_task`.

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env pytest tests/test_nodes.py -v`
Expected: PASS

### Task 4: Implement websocket route and graph streaming integration

**Files:**
- Create: `app/api/routes/ws_chat.py`
- Modify: `app/main.py`
- Test: `tests/test_ws_chat.py`

**Step 1: Write the failing test**

Confirm websocket route receives a user message and emits stage/token/final/end events.

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env pytest tests/test_ws_chat.py -v`
Expected: FAIL because route is missing

**Step 3: Write minimal implementation**

Map LangGraph `updates` to safe stage events and `custom` to token events.

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env pytest tests/test_ws_chat.py -v`
Expected: PASS

### Task 5: Scaffold frontend and implement warm chat UI

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.js`
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/index.css`
- Create: `frontend/src/ChatInterface.jsx`

**Step 1: Write the failing test**

No automated frontend test required for this task; validate by build/start commands.

**Step 2: Run setup verification**

Run: `npm --prefix frontend install`
Expected: dependencies installed

**Step 3: Write minimal implementation**

Create a React + Tailwind skeleton with warm colors, rounded cards, mic/video placeholders, websocket client, and referral card rendering.

**Step 4: Run frontend verification**

Run: `npm --prefix frontend run build`
Expected: build succeeds

### Task 6: Full verification and local-dev documentation

**Files:**
- Modify: `README.md`

**Step 1: Run backend tests**

Run: `conda run -n llm_env pytest -q`
Expected: PASS

**Step 2: Run frontend build**

Run: `npm --prefix frontend run build`
Expected: PASS

**Step 3: Update docs**

Document:
- backend start command
- frontend start command
- websocket URL
- optional mock webhook listener example
