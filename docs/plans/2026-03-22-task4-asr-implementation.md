# Task 4 Offline ASR Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an enterprise-grade local ASR service based on `faster-whisper`, with GPU/CPU auto fallback, VAD-assisted offline transcription, and a producer-consumer microphone streaming pipeline that yields completed utterances with low latency.

**Architecture:** The new module will live in `app/services/asr_service.py`. It will expose a reusable `FasterWhisperASRService` for file/array transcription and a `MicrophoneStreamTranscriber` for live microphone capture. The live path will use `sounddevice` for non-blocking audio capture, `webrtcvad` for speech boundary detection, `queue.Queue` for producer-consumer buffering, and a callback/generator interface for immediate downstream agent reactions.

**Tech Stack:** Python 3.11+, `faster-whisper`, `numpy`, `sounddevice`, `webrtcvad`

---

### Task 1: Add lightweight tests for ASR helper behavior

**Files:**
- Create: `tests/test_asr_service.py`

**Step 1: Write the failing test**

Add tests that validate:
- GPU/CPU compute configuration fallback logic
- concatenation of transcription segments into clean text
- speech-buffer flush conditions without needing a real microphone or model

**Step 2: Run test to verify it fails**

Run: `conda run -n llm_env pytest tests/test_asr_service.py -v`
Expected: FAIL because ASR module does not exist

### Task 2: Implement the local faster-whisper service

**Files:**
- Create: `app/services/asr_service.py`

**Step 1: Write minimal implementation**

Add:
- `WhisperSegment` data class
- `FasterWhisperASRService`
- robust model loading with CUDA auto detection and CPU fallback
- `transcribe_audio(audio_path_or_array)` with `vad_filter=True`

**Step 2: Run test to verify it passes**

Run: `conda run -n llm_env pytest tests/test_asr_service.py -v`
Expected: PASS

### Task 3: Implement live microphone producer-consumer pipeline

**Files:**
- Modify: `app/services/asr_service.py`

**Step 1: Extend implementation**

Add:
- background audio capture thread using `sounddevice.InputStream`
- `queue.Queue` transport for PCM frames
- `webrtcvad` speech boundary detection
- generator/callback based transcription output
- console-friendly `__main__` demo

**Step 2: Verify module imports**

Run: `conda run -n llm_env python -c "from app.services.asr_service import FasterWhisperASRService, MicrophoneStreamTranscriber; print('ok')"`
Expected: `ok`

### Task 4: Update dependencies and run full verification

**Files:**
- Modify: `requirements.txt`

**Step 1: Add runtime dependencies**

Add:
- `faster-whisper`
- `sounddevice`
- `webrtcvad`
- keep existing stack intact

**Step 2: Run focused and full verification**

Run:
- `conda run -n llm_env pytest tests/test_asr_service.py -v`
- `conda run -n llm_env pytest -q`

Expected: PASS
