# Voice Input Auto TTS Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make assistant replies auto-play spoken audio when the request is triggered by the frontend voice-input button, while keeping text-input replies text-only.

**Architecture:** Keep the existing backend streaming TTS path unchanged and fix the frontend voice-input pipeline instead. The voice websocket should always mark voice-originated turns with `response_audio: true` before audio bytes are processed, and the frontend playback queue should stay ready to consume explicit `tts_audio` / `tts_end` events without changing text-chat behavior.

**Tech Stack:** React 19, Vite, browser WebSocket audio streaming, node:test helper tests, FastAPI websocket backend (existing behavior reused)

---

### Task 1: Lock the desired request-shaping behavior with tests

**Files:**
- Modify: `frontend/src/hooks/useChatAgent.helpers.test.js`
- Modify: `frontend/src/hooks/useAudioStream.helpers.test.js`
- Test: `frontend/src/hooks/useChatAgent.helpers.test.js`
- Test: `frontend/src/hooks/useAudioStream.helpers.test.js`

**Step 1: Write the failing test**

Add a helper-level test proving that:
- voice-originated requests force `response_audio: true`
- text-originated requests keep `response_audio` tied to the explicit text-mode flag
- voice websocket control payloads include `input_mode: 'voice'` and the target sample rate

**Step 2: Run test to verify it fails**

Run: `node --test frontend/src/hooks/useChatAgent.helpers.test.js frontend/src/hooks/useAudioStream.helpers.test.js`
Expected: FAIL because the new helpers do not exist yet.

**Step 3: Write minimal implementation**

Implement tiny pure helpers for:
- shaping multimodal features by input source
- building websocket control payloads for the voice stream

**Step 4: Run test to verify it passes**

Run: `node --test frontend/src/hooks/useChatAgent.helpers.test.js frontend/src/hooks/useAudioStream.helpers.test.js`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/hooks/useChatAgent.helpers.* frontend/src/hooks/useAudioStream.helpers.*
git commit -m "test: cover voice input auto tts request shaping"
```

### Task 2: Wire the voice-input path to request spoken replies

**Files:**
- Modify: `frontend/src/hooks/useChatAgent.js`
- Modify: `frontend/src/hooks/useAudioStream.js`

**Step 1: Write the failing test**

Reuse the helper tests from Task 1 as the red phase for the request-shaping logic.

**Step 2: Run test to verify it fails**

Run: `node --test frontend/src/hooks/useChatAgent.helpers.test.js frontend/src/hooks/useAudioStream.helpers.test.js`
Expected: FAIL before the helpers and hook wiring are added.

**Step 3: Write minimal implementation**

Update the hooks so that:
- voice websocket context is primed before audio chunks are streamed
- commit payloads are built from the new helper
- voice-stream multimodal features always request response audio
- the playback queue remains enabled to consume explicit TTS events

**Step 4: Run targeted verification**

Run: `node --test frontend/src/hooks/useChatAgent.helpers.test.js frontend/src/hooks/useAudioStream.helpers.test.js`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/hooks/useChatAgent.js frontend/src/hooks/useAudioStream.js
git commit -m "feat: auto play tts for voice input turns"
```

### Task 3: Verify no backend regression in existing TTS websocket flow

**Files:**
- Test: `tests/test_ws_chat.py`

**Step 1: Run focused backend verification**

Run: `conda run -n llm_env python -m pytest -q --tb=short tests/test_ws_chat.py -k tts`
Expected: PASS

**Step 2: Run focused frontend verification**

Run: `node --test frontend/src/hooks/useChatAgent.helpers.test.js frontend/src/hooks/useAudioStream.helpers.test.js`
Expected: PASS

**Step 3: Summarize residual risk**

Document that browser autoplay policy may still require a user gesture on some platforms, but the code path now requests and consumes TTS for voice-button turns correctly.

