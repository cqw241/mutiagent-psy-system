# Task 2 Memory And RAGFlow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add session-level memory with LangGraph `MemorySaver` and integrate RAGFlow retrieval through a dedicated graph node that writes `reference_context` into shared state before risk assessment.

**Architecture:** The graph will be refactored from three nodes to four nodes, with memory handled by a LangGraph checkpointer keyed by `session_id`. Retrieval will move into a dedicated async `rag_retriever_node`, while `risk_assessor_node` will consume `reference_context` rather than calling external retrieval directly.

**Tech Stack:** Python 3.11+, FastAPI, LangGraph, MemorySaver, httpx, LiteLLM, Pytest

---

### Task 1: Extend state and schemas for memory-driven execution

**Files:**
- Modify: `app/graph/state.py`
- Modify: `app/models/schemas.py`
- Test: `tests/test_state_schema.py`

**Step 1: Write the failing test**

Add a test that asserts `reference_context` exists in `PsychologyGraphState` and that `chat_history` is append-oriented.

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env pytest tests/test_state_schema.py -v`
Expected: FAIL because `reference_context` is missing

**Step 3: Write minimal implementation**

Add `reference_context` to state and prepare `chat_history` for reducer-based accumulation.

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env pytest tests/test_state_schema.py -v`
Expected: PASS

### Task 2: Add async RAGFlow client with graceful degradation

**Files:**
- Create: `app/rag/__init__.py`
- Create: `app/rag/ragflow_client.py`
- Modify: `app/core/config.py`
- Test: `tests/test_ragflow_client.py`

**Step 1: Write the failing test**

Create tests for:
- successful retrieval returns merged chunk content
- timeout returns empty string
- malformed response returns empty string

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env pytest tests/test_ragflow_client.py -v`
Expected: FAIL because client does not exist

**Step 3: Write minimal implementation**

Implement async `retrieve_similar_cases(query: str, top_k: int = 3) -> str`.

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env pytest tests/test_ragflow_client.py -v`
Expected: PASS

### Task 3: Add dedicated `rag_retriever_node`

**Files:**
- Create: `app/nodes/rag_retriever.py`
- Test: `tests/test_rag_retriever_node.py`

**Step 1: Write the failing test**

Test that the node reads the latest user message, calls the client, and writes `reference_context` into state.

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env pytest tests/test_rag_retriever_node.py -v`
Expected: FAIL because node does not exist

**Step 3: Write minimal implementation**

Implement async node with safe fallback to `reference_context = ""`.

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env pytest tests/test_rag_retriever_node.py -v`
Expected: PASS

### Task 4: Upgrade `risk_assessor_node` to consume `reference_context`

**Files:**
- Modify: `app/nodes/risk_assessor.py`
- Test: `tests/test_nodes.py`

**Step 1: Write the failing test**

Add a test that checks `agent_judgments["risk_assessor"]` records that reference context was used, and that the prompt path remains safe when context is empty.

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env pytest tests/test_nodes.py -v`
Expected: FAIL because node does not consume `reference_context`

**Step 3: Write minimal implementation**

Read `reference_context` from state and include `<Reference_Cases>` in the system prompt.

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env pytest tests/test_nodes.py -v`
Expected: PASS

### Task 5: Refactor graph compilation to use `MemorySaver`

**Files:**
- Modify: `app/graph/workflow.py`
- Test: `tests/test_workflow.py`
- Test: `tests/test_graph_integration.py`

**Step 1: Write the failing test**

Add an integration test that invokes the graph twice with the same `thread_id` and verifies prior history remains available.

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env pytest tests/test_workflow.py tests/test_graph_integration.py -v`
Expected: FAIL because graph has no checkpointer

**Step 3: Write minimal implementation**

Compile with `MemorySaver` and insert `rag_retriever_node` into the routing chain.

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env pytest tests/test_workflow.py tests/test_graph_integration.py -v`
Expected: PASS

### Task 6: Upgrade `/chat` to thread-aware async execution

**Files:**
- Modify: `app/api/routes/chat.py`
- Test: `tests/test_chat_api.py`

**Step 1: Write the failing test**

Add a test that posts twice with the same `session_id` and verifies the stored history grows or that the graph path uses session memory.

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env pytest tests/test_chat_api.py -v`
Expected: FAIL because route does not use `thread_id`

**Step 3: Write minimal implementation**

Convert route to async and call `compiled_graph.ainvoke(..., config={\"configurable\": {\"thread_id\": session_id}})`.

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env pytest tests/test_chat_api.py -v`
Expected: PASS

### Task 7: Refresh docs and run full verification

**Files:**
- Modify: `README.md`

**Step 1: Write the failing test**

No dedicated failing doc test; rely on full suite.

**Step 2: Run verification before docs update**

Run: `conda run -n llm_env pytest -q`
Expected: PASS before final README update

**Step 3: Write minimal implementation**

Document:
- session memory behavior
- RAGFlow env vars
- mock testing approach for RAGFlow

**Step 4: Run full verification**

Run: `conda run -n llm_env pytest -q`
Expected: PASS
