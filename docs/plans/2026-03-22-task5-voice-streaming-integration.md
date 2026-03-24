# Task 5 Voice Streaming Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect the React frontend microphone to the FastAPI backend over WebSocket, stream raw PCM audio into VAD + faster-whisper, feed each completed utterance into the existing LangGraph workflow, and stream transcript plus assistant reply events back to the UI.

**Architecture:** Keep the existing `/ws/chat/{session_id}` text route intact and add a dedicated voice route that accepts binary PCM audio frames and lightweight JSON control messages. Reuse the current `SpeechBufferState` and VAD thresholds by introducing a chunk-fed audio adapter inside `app/services/asr_service.py`, then forward completed transcript text into the same compiled LangGraph instance so the token/final event contract remains familiar to the frontend.

**Tech Stack:** FastAPI WebSocket, webrtcvad, faster-whisper, NumPy, React 19, Web Audio API, Tailwind CSS v4, Vite.

---

### Task 1: Define Backend Streaming Contract

**Files:**
- Modify: `tests/test_asr_service.py`
- Modify: `tests/test_ws_chat.py`

**Step 1: Write the failing tests**

Add tests for:
- feeding PCM bytes across uneven chunk boundaries and only flushing after enough silence
- forcing a final flush when the client sends a stop control event
- receiving `transcript`, `stage`, `token`, `final`, and `end` events from `/ws/voice-chat/{session_id}`

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env --no-capture-output python -m pytest -q tests/test_asr_service.py tests/test_ws_chat.py`

Expected: FAIL because the PCM adapter and voice WebSocket route do not exist yet.

**Step 3: Write minimal implementation**

Implement only the adapter interfaces and route behavior required by the tests.

**Step 4: Run test to verify it passes**

Run: `conda run -n llm_env --no-capture-output python -m pytest -q tests/test_asr_service.py tests/test_ws_chat.py`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_asr_service.py tests/test_ws_chat.py app/services/asr_service.py app/api/routes/ws_chat.py app/main.py
git commit -m "feat: add voice websocket backend pipeline"
```

### Task 2: Implement Frontend Microphone Transport

**Files:**
- Create: `frontend/src/hooks/useAudioStream.js`
- Modify: `frontend/src/ChatInterface.jsx`

**Step 1: Write the failing test**

For this repo, prefer behavior-driven manual verification plus production build because no frontend test runner is configured yet. The failing condition is a broken build or a UI that cannot open the microphone and WebSocket cleanly.

**Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run build`

Expected: If the new hook is referenced before being implemented, the build fails.

**Step 3: Write minimal implementation**

Implement:
- browser microphone capture with `AudioContext`
- mono mixdown, 16kHz downsampling, and `Int16Array` serialization
- voice route WebSocket lifecycle
- transcript/assistant stream rendering and graceful disconnect cleanup

**Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run build`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/hooks/useAudioStream.js frontend/src/ChatInterface.jsx
git commit -m "feat: add browser voice streaming client"
```

### Task 3: Verify End-to-End Integration

**Files:**
- Review only: `app/api/routes/ws_chat.py`
- Review only: `app/services/asr_service.py`
- Review only: `frontend/src/ChatInterface.jsx`

**Step 1: Run backend verification**

Run: `conda run -n llm_env --no-capture-output python -m pytest -q tests/test_asr_service.py tests/test_ws_chat.py tests/test_chat_api.py`

Expected: PASS

**Step 2: Run frontend verification**

Run: `npm --prefix frontend run build`

Expected: PASS

**Step 3: Review protocol checklist**

Confirm:
- binary input uses raw PCM int16 16kHz mono
- client can explicitly flush remaining speech on stop
- server sends transcript event before LangGraph stage/token/final events
- text chat route still behaves as before

**Step 4: Commit**

```bash
git add docs/plans/2026-03-22-task5-voice-streaming-integration.md
git commit -m "docs: add task 5 implementation plan"
```
