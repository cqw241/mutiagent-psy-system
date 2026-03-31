import asyncio
from typing import Any

import numpy as np

from app.core.config import get_settings
from app.nodes.text_analyzer import text_analyzer_node
from app.nodes.voice_analyzer import voice_analyzer_node
from app.nodes.face_analyzer import face_analyzer_node
from app.nodes.information_extractor import information_extractor_node
from app.nodes.signal_aggregator import signal_aggregator_node
from app.nodes.risk_assessor import risk_assessor_node
from app.nodes.response_generator import response_generator_node
from app.nodes.referral_agent import referral_agent_node


class DummyRiskLLM:
    def complete_json(self, system_prompt: str, user_prompt: str):
        return {"risk_level": "medium", "risk_score": "not-a-number", "reason": "bad output"}


class DummyLowRiskLLM:
    def complete_json(self, system_prompt: str, user_prompt: str):
        return {"risk_level": "low", "risk_score": 0.2, "reason": "benign"}


class DummyBenignHighRiskLLM:
    def complete_json(self, system_prompt: str, user_prompt: str):
        return {"risk_level": "high", "risk_score": 0.98, "reason": "over-sensitive output"}


class DummyUnsafeHighRiskLLM:
    def complete_json(self, system_prompt: str, user_prompt: str):
        return {"reply": "你自己判断吧"}


class DummyStreamingLLM:
    def __init__(self):
        self.complete_json_calls = 0
        self.stream_prompts = []

    def complete_json(self, system_prompt: str, user_prompt: str):
        self.complete_json_calls += 1
        return {"reply": "忽略这个字段"}

    async def stream_text(self, system_prompt: str, user_prompt: str, fallback_text: str):
        self.stream_prompts.append((system_prompt, user_prompt, fallback_text))
        for chunk in ["我", "会", "陪", "着", "你"]:
            yield chunk


class DummyExtractorLLM:
    def complete_json(self, system_prompt: str, user_prompt: str):
        return {
            "emotion_keywords": ["焦虑"],
            "sentiment": "stressed",
            "observations": ["文本提到临近考试，压力较高"],
        }


class PromptRecordingLLM:
    def __init__(self, response: dict[str, Any]):
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system_prompt: str, user_prompt: str):
        self.calls.append((system_prompt, user_prompt))
        return self.response


class DummyAsyncAlertService:
    def __init__(self):
        self.payload = None

    def send_high_risk_alert(self, payload):
        return {"sent": True}

    async def send_high_risk_alert_async(self, payload):
        self.payload = payload
        return {"sent": True}


class DummyVoiceEmotionLLM:
    def complete_json(self, system_prompt: str, user_prompt: str):
        return {
            "observation": "语音表现平稳。",
            "emotion_label": "neutral",
            "confidence": 0.6,
        }


class DummyEmotion2VecService:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls = 0

    def analyze(self, audio):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def _set_emotion2vec_env(monkeypatch, **env):
    managed_keys = {
        "ENABLE_EMOTION2VEC",
        "EMOTION2VEC_MODEL_DIR",
        "EMOTION2VEC_SAMPLE_RATE",
    }
    for key in managed_keys:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


# ── Text Analyzer Tests ──


def test_text_analyzer_extracts_keywords():
    state = {
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "快考试了，我有点焦虑"}],
        "multimodal_features": {},
        "agent_judgments": {},
    }
    updated = text_analyzer_node(state, llm_client=DummyExtractorLLM())
    assert "焦虑" in updated["text_signals"]["emotion_keywords"]
    assert updated["agent_judgments"]["text_analyzer"]["used_llm"] is True


def test_text_analyzer_does_not_extract_acoustic_observations():
    """text_analyzer should NOT handle acoustic features (that's voice_analyzer's job)."""
    state = {
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "快考试了，我有点慌"}],
        "multimodal_features": {
            "voice_acoustic_features": {
                "pause_count": 4,
                "pause_total_ms": 2200,
            }
        },
        "agent_judgments": {},
    }
    updated = text_analyzer_node(state, llm_client=DummyExtractorLLM())
    assert "acoustic_observations" not in updated["text_signals"]


def test_text_analyzer_uses_centralized_prompt_builder(monkeypatch):
    llm = PromptRecordingLLM(
        {
            "emotion_keywords": ["焦虑"],
            "sentiment": "stressed",
            "observations": ["考试压力较高"],
        }
    )
    monkeypatch.setattr(
        "app.nodes.text_analyzer.build_text_analyzer_prompts",
        lambda *_args, **_kwargs: ("text-system-sentinel", "text-user-sentinel"),
        raising=False,
    )
    state = {
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "最近有些焦虑"}],
        "multimodal_features": {},
        "agent_judgments": {},
    }

    text_analyzer_node(state, llm_client=llm)

    assert llm.calls == [("text-system-sentinel", "text-user-sentinel")]


def test_information_extractor_uses_centralized_prompt_builder(monkeypatch):
    llm = PromptRecordingLLM(
        {
            "emotion_keywords": ["焦虑"],
            "sentiment": "stressed",
            "observations": ["多模态线索提示考试压力"],
        }
    )
    monkeypatch.setattr(
        "app.nodes.information_extractor.build_information_extractor_prompts",
        lambda *_args, **_kwargs: ("info-system-sentinel", "info-user-sentinel"),
        raising=False,
    )
    state = {
        "session_id": "sess-info-1",
        "chat_history": [{"role": "user", "content": "最近有点焦虑"}],
        "multimodal_features": {
            "voice_acoustic_features": {
                "pause_count": 3,
                "pause_total_ms": 1800,
            }
        },
        "agent_judgments": {},
    }

    updated = information_extractor_node(state, llm_client=llm)

    assert llm.calls == [("info-system-sentinel", "info-user-sentinel")]
    assert updated["extracted_signals"]["emotion_keywords"] == ["焦虑"]


# ── Voice Analyzer Tests ──


def test_voice_analyzer_extracts_from_precomputed_features(monkeypatch):
    _set_emotion2vec_env(monkeypatch, ENABLE_EMOTION2VEC="false")
    state = {
        "session_id": "sess-voice-1",
        "chat_history": [{"role": "user", "content": "快考试了，我有点慌"}],
        "multimodal_features": {
            "voice_acoustic_features": {
                "pause_count": 4,
                "pause_total_ms": 2200,
                "pause_mean_ms": 550.0,
                "voiced_duration_ms": 1800,
                "speech_ratio": 0.42,
                "mean_f0": None,
                "f0_std": None,
                "energy_mean": 0.02,
                "energy_std": 0.0004,
                "rms_mean": 0.09,
                "rms_std": 0.005,
            }
        },
        "voice_segments": [],
        "agent_judgments": {},
    }
    updated = asyncio.run(voice_analyzer_node(state))
    obs = updated["voice_signals"]["acoustic_observations"]
    assert "pause_total_ms_high" in obs
    assert "speech_ratio_low" in obs
    assert "energy_variability_low" in obs
    assert updated["voice_signals"]["emotion2vec_reading"]["status"] == "disabled"
    assert updated["agent_judgments"]["voice_analyzer"]["has_voice_data"] is True


def test_voice_analyzer_reuses_precomputed_emotion2vec_reading_without_raw_audio(
    monkeypatch,
):
    _set_emotion2vec_env(
        monkeypatch,
        ENABLE_EMOTION2VEC="true",
        EMOTION2VEC_MODEL_DIR="/tmp/emotion2vec",
    )
    reading = {
        "status": "ok",
        "source": "emotion2vec_plus_large",
        "model_dir": "/tmp/emotion2vec",
        "emotion_label": "sad",
        "confidence": 0.82,
        "topk": [{"label": "sad", "score": 0.82}],
        "observation": "语音情绪类别更接近 sad。",
        "raw_output": {"labels": ["sad"], "scores": [0.82]},
        "error": None,
    }
    state = {
        "chat_history": [{"role": "user", "content": "最近说话有点沉"}],
        "multimodal_features": {},
        "voice_segments": [
            {
                "segment_id": "seg-1",
                "acoustic_features": {
                    "pause_count": 4,
                    "pause_total_ms": 2200,
                    "pause_mean_ms": 550.0,
                    "voiced_duration_ms": 1800,
                    "speech_ratio": 0.42,
                    "mean_f0": None,
                    "f0_std": None,
                    "energy_mean": 0.02,
                    "energy_std": 0.0004,
                    "rms_mean": 0.09,
                    "rms_std": 0.005,
                },
                "emotion2vec_reading": reading,
            }
        ],
        "agent_judgments": {},
    }

    try:
        updated = asyncio.run(voice_analyzer_node(state))
    finally:
        get_settings.cache_clear()

    assert updated["voice_signals"]["emotion2vec_reading"] == reading
    judgment = updated["agent_judgments"]["voice_analyzer"]
    assert judgment["emotion2vec_enabled"] is True
    assert judgment["emotion2vec_used"] is True
    assert judgment["emotion2vec_status"] == "ok"
    assert judgment["emotion2vec_label"] == "sad"


def test_voice_analyzer_uses_segment_features_over_multimodal():
    state = {
        "chat_history": [],
        "multimodal_features": {
            "voice_acoustic_features": {"pause_count": 0}
        },
        "voice_segments": [
            {
                "segment_id": "seg-1",
                "acoustic_features": {
                    "pause_count": 5,
                    "pause_total_ms": 3000,
                    "voiced_duration_ms": 2000,
                    "speech_ratio": 0.35,
                },
            }
        ],
        "agent_judgments": {},
    }
    updated = asyncio.run(voice_analyzer_node(state))
    assert "pause_total_ms_high" in updated["voice_signals"]["acoustic_observations"]
    assert updated["agent_judgments"]["voice_analyzer"]["feature_source"] == "precomputed_segment"


def test_voice_analyzer_returns_degraded_for_no_features(monkeypatch):
    _set_emotion2vec_env(monkeypatch, ENABLE_EMOTION2VEC="false")
    state = {
        "chat_history": [],
        "multimodal_features": {},
        "voice_segments": [],
        "agent_judgments": {},
    }
    updated = asyncio.run(voice_analyzer_node(state))
    assert updated["voice_signals"]["status"] == "degraded"
    assert updated["voice_signals"]["confidence"] == 0
    assert updated["voice_signals"]["acoustic_observations"] == []
    assert updated["voice_signals"]["emotion2vec_reading"]["status"] == "disabled"


def test_voice_analyzer_processes_raw_audio_with_full_pipeline(monkeypatch):
    """Test the full pipeline: raw PCM → physical features + MFCC + emotion heuristic."""
    _set_emotion2vec_env(monkeypatch, ENABLE_EMOTION2VEC="false")
    # Generate a synthetic 500ms sine wave with pauses
    sr = 16000
    t = np.arange(int(sr * 0.3), dtype=np.float32) / sr
    voiced = 0.3 * np.sin(2 * np.pi * 180 * t)
    silence = np.zeros(int(sr * 0.2), dtype=np.float32)
    audio = np.concatenate([voiced, silence, voiced]).astype(np.float32)

    state = {
        "chat_history": [{"role": "user", "content": "我最近压力很大"}],
        "multimodal_features": {
            "audio_pcm": audio,
        },
        "voice_segments": [],
        "agent_judgments": {},
    }
    updated = asyncio.run(
        voice_analyzer_node(state, llm_client=DummyVoiceEmotionLLM())
    )

    vs = updated["voice_signals"]
    assert vs["status"] == "ok"
    assert vs["features"] is not None
    assert vs["features"]["energy_mean"] > 0
    assert vs["mfcc_features"] is not None
    assert vs["mfcc_features"]["n_mfcc"] == 13
    assert vs["emotion_heuristic"] is not None
    assert vs["emotion2vec_reading"]["status"] == "disabled"
    assert "dominant_cue" in vs["emotion_heuristic"]

    jdg = updated["agent_judgments"]["voice_analyzer"]
    assert jdg["feature_source"] == "raw_audio"
    assert jdg["mfcc_extracted"] is True
    assert jdg["emotion2vec_status"] == "disabled"


def test_voice_analyzer_uses_centralized_prompt_builder(monkeypatch):
    _set_emotion2vec_env(monkeypatch, ENABLE_EMOTION2VEC="false")
    llm = PromptRecordingLLM(
        {
            "observation": "语音表现平稳。",
            "emotion_label": "neutral",
            "confidence": 0.6,
        }
    )
    monkeypatch.setattr(
        "app.nodes.voice_analyzer._extract_all_features",
        lambda _audio: {
            "physical_features": {"energy_mean": 0.1},
            "mfcc_features": {"n_mfcc": 13, "n_frames": 2},
            "emotion_heuristic": {"dominant_cue": "stable", "confidence": 0.6},
        },
    )
    monkeypatch.setattr(
        "app.nodes.voice_analyzer.extract_acoustic_observations",
        lambda _features: ["speech_ratio_low"],
    )
    monkeypatch.setattr(
        "app.nodes.voice_analyzer.build_voice_analyzer_prompts",
        lambda *_args, **_kwargs: ("voice-system-sentinel", "voice-user-sentinel"),
        raising=False,
    )
    state = {
        "chat_history": [{"role": "user", "content": "最近说话有点慢"}],
        "multimodal_features": {"audio_pcm": np.array([0.1, -0.1], dtype=np.float32)},
        "voice_segments": [],
        "agent_judgments": {},
    }

    asyncio.run(voice_analyzer_node(state, llm_client=llm))

    assert llm.calls == [("voice-system-sentinel", "voice-user-sentinel")]


def test_voice_analyzer_adds_emotion2vec_reading_without_breaking_legacy_pipeline(
    monkeypatch,
):
    _set_emotion2vec_env(
        monkeypatch,
        ENABLE_EMOTION2VEC="true",
        EMOTION2VEC_MODEL_DIR="/tmp/emotion2vec",
    )
    service = DummyEmotion2VecService(
        result={
            "status": "ok",
            "source": "emotion2vec_plus_large",
            "model_dir": "/tmp/emotion2vec",
            "emotion_label": "sad",
            "confidence": 0.81,
            "topk": [{"label": "sad", "score": 0.81}],
            "observation": "语音情绪类别更接近 sad。",
            "raw_output": {"labels": ["sad"], "scores": [0.81]},
            "error": None,
        }
    )
    monkeypatch.setattr(
        "app.nodes.voice_analyzer.get_emotion2vec_service",
        lambda _settings: service,
    )

    sr = 16000
    t = np.arange(int(sr * 0.25), dtype=np.float32) / sr
    audio = (0.2 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
    state = {
        "chat_history": [{"role": "user", "content": "最近有些累"}],
        "multimodal_features": {"audio_pcm": audio},
        "voice_segments": [],
        "agent_judgments": {},
    }

    try:
        updated = asyncio.run(
            voice_analyzer_node(state, llm_client=DummyVoiceEmotionLLM())
        )
    finally:
        get_settings.cache_clear()

    voice_signals = updated["voice_signals"]
    assert voice_signals["status"] == "ok"
    assert voice_signals["features"]["energy_mean"] > 0
    assert voice_signals["emotion2vec_reading"]["status"] == "ok"
    assert voice_signals["emotion2vec_reading"]["emotion_label"] == "sad"

    judgment = updated["agent_judgments"]["voice_analyzer"]
    assert judgment["emotion2vec_enabled"] is True
    assert judgment["emotion2vec_used"] is True
    assert judgment["emotion2vec_status"] == "ok"
    assert judgment["emotion2vec_label"] == "sad"
    assert service.calls == 1


def test_voice_analyzer_degrades_emotion2vec_errors_without_breaking_legacy_fields(
    monkeypatch,
):
    _set_emotion2vec_env(
        monkeypatch,
        ENABLE_EMOTION2VEC="true",
        EMOTION2VEC_MODEL_DIR="/tmp/emotion2vec",
    )
    monkeypatch.setattr(
        "app.nodes.voice_analyzer.get_emotion2vec_service",
        lambda _settings: DummyEmotion2VecService(error=RuntimeError("boom")),
    )

    sr = 16000
    t = np.arange(int(sr * 0.2), dtype=np.float32) / sr
    audio = (0.2 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
    state = {
        "chat_history": [{"role": "user", "content": "最近压力有点大"}],
        "multimodal_features": {"audio_pcm": audio},
        "voice_segments": [],
        "agent_judgments": {},
    }

    try:
        updated = asyncio.run(
            voice_analyzer_node(state, llm_client=DummyVoiceEmotionLLM())
        )
    finally:
        get_settings.cache_clear()

    voice_signals = updated["voice_signals"]
    assert voice_signals["status"] == "ok"
    assert voice_signals["features"]["energy_mean"] > 0
    assert voice_signals["emotion2vec_reading"]["status"] == "error"
    assert voice_signals["emotion2vec_reading"]["error"] == "boom"

    judgment = updated["agent_judgments"]["voice_analyzer"]
    assert judgment["emotion2vec_enabled"] is True
    assert judgment["emotion2vec_used"] is False
    assert judgment["emotion2vec_status"] == "error"
    assert judgment["emotion2vec_label"] is None


def test_voice_analyzer_marks_emotion2vec_unavailable_without_raw_audio(monkeypatch):
    _set_emotion2vec_env(
        monkeypatch,
        ENABLE_EMOTION2VEC="true",
        EMOTION2VEC_MODEL_DIR="/tmp/emotion2vec",
    )
    state = {
        "chat_history": [{"role": "user", "content": "说话有点慢"}],
        "multimodal_features": {
            "voice_acoustic_features": {
                "pause_count": 4,
                "pause_total_ms": 2200,
                "voiced_duration_ms": 1800,
                "speech_ratio": 0.42,
            }
        },
        "voice_segments": [],
        "agent_judgments": {},
    }

    try:
        updated = asyncio.run(voice_analyzer_node(state))
    finally:
        get_settings.cache_clear()

    reading = updated["voice_signals"]["emotion2vec_reading"]
    assert reading["status"] == "unavailable"
    assert reading["emotion_label"] is None

    judgment = updated["agent_judgments"]["voice_analyzer"]
    assert judgment["emotion2vec_enabled"] is True
    assert judgment["emotion2vec_used"] is False
    assert judgment["emotion2vec_status"] == "unavailable"


# ── Face Analyzer Tests ──


def test_face_analyzer_extracts_emotion_from_facial_data():
    """Legacy pathway: multimodal_features.facial_data.emotion → observation."""
    state = {
        "multimodal_features": {
            "facial_data": {"emotion": "sad"},
        },
        "face_segments": [],
        "agent_judgments": {},
    }
    updated = face_analyzer_node(state)
    assert "facial_expression_sad" in updated["face_signals"]["facial_observations"]
    assert updated["face_signals"]["dominant_blend"] == "sad"
    assert updated["agent_judgments"]["face_analyzer"]["feature_source"] == "legacy_multimodal"


def test_face_analyzer_extracts_from_legacy_facial_emotion():
    """Legacy pathway: multimodal_features.facial_emotion → observation."""
    state = {
        "multimodal_features": {
            "facial_emotion": "angry",
        },
        "face_segments": [],
        "agent_judgments": {},
    }
    updated = face_analyzer_node(state)
    assert "facial_expression_angry" in updated["face_signals"]["facial_observations"]


def test_face_analyzer_handles_missing_data():
    """No face data at all → empty observations, graceful defaults."""
    state = {
        "multimodal_features": {},
        "face_segments": [],
        "agent_judgments": {},
    }
    updated = face_analyzer_node(state)
    assert updated["face_signals"]["facial_observations"] == []
    assert updated["face_signals"]["dominant_blend"] == "unknown"
    assert updated["agent_judgments"]["face_analyzer"]["feature_source"] == "none"


def test_face_analyzer_maps_high_au04_to_frown_observation():
    """AU04 > 0.6 should produce '用户持续皱眉（眉部紧缩）'."""
    state = {
        "multimodal_features": {},
        "face_segments": [
            {
                "timestamp_ms": 1000,
                "action_units": {"AU04": 0.8},
                "blend_scores": {},
            }
        ],
        "agent_judgments": {},
    }
    updated = face_analyzer_node(state)
    obs = updated["face_signals"]["facial_observations"]
    assert any("皱眉" in o for o in obs)
    assert updated["agent_judgments"]["face_analyzer"]["feature_source"] == "face_segments"


def test_face_analyzer_ignores_low_au_values():
    """AU values below threshold should NOT trigger observations."""
    state = {
        "multimodal_features": {},
        "face_segments": [
            {
                "timestamp_ms": 2000,
                "action_units": {"AU04": 0.2, "AU15": 0.1, "AU01": 0.3},
                "blend_scores": {},
            }
        ],
        "agent_judgments": {},
    }
    updated = face_analyzer_node(state)
    assert updated["face_signals"]["facial_observations"] == []


def test_face_analyzer_applies_compound_rules():
    """AU06 + AU12 both > 0.5 should produce '面部呈现微笑'."""
    state = {
        "multimodal_features": {},
        "face_segments": [
            {
                "timestamp_ms": 3000,
                "action_units": {"AU06": 0.7, "AU12": 0.8},
                "blend_scores": {"happy": 0.85, "neutral": 0.15},
            }
        ],
        "agent_judgments": {},
    }
    updated = face_analyzer_node(state)
    obs = updated["face_signals"]["facial_observations"]
    assert any("微笑" in o for o in obs)
    assert updated["face_signals"]["dominant_blend"] == "happy"
    assert updated["face_signals"]["dominant_confidence"] == 0.85


def test_face_analyzer_extracts_dominant_blend():
    """blend_scores present → dominant emotion extracted with confidence."""
    state = {
        "multimodal_features": {},
        "face_segments": [
            {
                "timestamp_ms": 4000,
                "action_units": {},
                "blend_scores": {"sad": 0.67, "happy": 0.12, "neutral": 0.21},
            }
        ],
        "agent_judgments": {},
    }
    updated = face_analyzer_node(state)
    assert updated["face_signals"]["dominant_blend"] == "sad"
    assert updated["face_signals"]["dominant_confidence"] == 0.67


def test_face_analyzer_uses_latest_segment():
    """When multiple segments exist, only the latest (last) is analyzed."""
    state = {
        "multimodal_features": {},
        "face_segments": [
            {
                "timestamp_ms": 1000,
                "action_units": {"AU04": 0.9},
                "blend_scores": {},
            },
            {
                "timestamp_ms": 2000,
                "action_units": {"AU12": 0.8},
                "blend_scores": {"happy": 0.9},
            },
        ],
        "agent_judgments": {},
    }
    updated = face_analyzer_node(state)
    obs = updated["face_signals"]["facial_observations"]
    # Latest segment has AU12 (嘴角上扬) not AU04 (皱眉)
    assert any("嘴角上扬" in o for o in obs)
    assert not any("皱眉" in o for o in obs)
    assert updated["face_signals"]["segment_count"] == 2


# ── Signal Aggregator Tests ──


def test_signal_aggregator_merges_all_sources():
    state = {
        "text_signals": {
            "emotion_keywords": ["焦虑"],
            "sentiment": "stressed",
            "observations": ["考试压力"],
        },
        "voice_signals": {
            "acoustic_observations": ["pause_total_ms_high"],
        },
        "face_signals": {
            "facial_observations": ["facial_expression_sad"],
            "dominant_blend": "sad",
            "dominant_confidence": 0.67,
            "au_summary": {},
        },
        "agent_judgments": {},
    }
    updated = signal_aggregator_node(state)
    signals = updated["extracted_signals"]
    assert signals["emotion_keywords"] == ["焦虑"]
    assert signals["acoustic_observations"] == ["pause_total_ms_high"]
    assert signals["facial_observations"] == ["facial_expression_sad"]
    sources = updated["agent_judgments"]["signal_aggregator"]["sources_used"]
    assert "text_analyzer" in sources
    assert "voice_analyzer" in sources
    assert "face_analyzer" in sources


def test_signal_aggregator_works_with_text_only():
    state = {
        "text_signals": {
            "emotion_keywords": ["失眠"],
            "sentiment": "unknown",
        },
        "voice_signals": {},
        "face_signals": {},
        "agent_judgments": {},
    }
    updated = signal_aggregator_node(state)
    assert updated["extracted_signals"]["emotion_keywords"] == ["失眠"]
    assert updated["extracted_signals"]["acoustic_observations"] == []
    assert updated["extracted_signals"]["facial_observations"] == []


# ── Risk Assessor Tests ──


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


def test_risk_assessor_handles_malformed_llm_score_safely():
    state = {
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "最近很痛苦"}],
        "multimodal_features": {},
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {"emotion_keywords": ["痛苦"]},
        "risk_level": "low",
        "referral_required": False,
    }
    updated = risk_assessor_node(state, llm_client=DummyRiskLLM())
    assert updated["risk_level"] == "medium"
    assert updated["current_risk_score"] == 0.6
    assert updated["agent_judgments"]["risk_assessor"]["reference_context_used"] is False


def test_risk_assessor_marks_reference_context_usage():
    state = {
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "最近很痛苦"}],
        "multimodal_features": {},
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {"emotion_keywords": ["痛苦"]},
        "reference_context": "案例A：出现持续失眠与绝望表达时需要提高风险关注。",
        "risk_level": "low",
        "referral_required": False,
    }
    updated = risk_assessor_node(state, llm_client=DummyRiskLLM())
    assert updated["agent_judgments"]["risk_assessor"]["reference_context_used"] is True


def test_risk_assessor_uses_centralized_prompt_builder(monkeypatch):
    llm = PromptRecordingLLM(
        {
            "risk_level": "medium",
            "risk_score": 0.65,
            "reason": "需要更多支持",
        }
    )
    monkeypatch.setattr(
        "app.nodes.risk_assessor.build_risk_assessor_prompts",
        lambda *_args, **_kwargs: ("risk-system-sentinel", "risk-user-sentinel"),
        raising=False,
    )
    state = {
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "最近很痛苦"}],
        "multimodal_features": {},
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {"emotion_keywords": ["痛苦"]},
        "reference_context": "",
        "risk_level": "low",
        "referral_required": False,
    }

    risk_assessor_node(state, llm_client=llm)

    assert llm.calls == [("risk-system-sentinel", "risk-user-sentinel")]


def test_risk_assessor_does_not_escalate_benign_message_from_llm_misfire():
    state = {
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "我现在心情好起来了，你能陪我聊天吗？"}],
        "multimodal_features": {},
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {"emotion_keywords": []},
        "reference_context": "",
        "risk_level": "low",
        "referral_required": False,
    }
    updated = risk_assessor_node(state, llm_client=DummyBenignHighRiskLLM())
    assert updated["risk_level"] == "low"
    assert updated["referral_required"] is False


def test_risk_assessor_does_not_flag_exam_stress_as_high_risk():
    state = {
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "我都说了快考试我复习不完了"}],
        "multimodal_features": {},
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {"emotion_keywords": []},
        "reference_context": "",
        "risk_level": "low",
        "referral_required": False,
    }
    updated = risk_assessor_node(state, llm_client=DummyBenignHighRiskLLM())
    assert updated["risk_level"] != "high"
    assert updated["referral_required"] is False


def test_risk_assessor_flags_explicit_self_harm_blacklist_phrase():
    state = {
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "我真的不想活了"}],
        "multimodal_features": {},
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {"emotion_keywords": []},
        "reference_context": "",
        "risk_level": "low",
        "referral_required": False,
    }
    updated = risk_assessor_node(state, llm_client=DummyRiskLLM())
    assert updated["risk_level"] == "high"
    assert updated["referral_required"] is True


def test_risk_assessor_does_not_flag_non_self_harm_jietuo_context():
    state = {
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "终于考完试了，我一下子解脱了"}],
        "multimodal_features": {},
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {"emotion_keywords": []},
        "reference_context": "",
        "risk_level": "low",
        "referral_required": False,
    }
    updated = risk_assessor_node(state, llm_client=DummyBenignHighRiskLLM())
    assert updated["risk_level"] != "high"
    assert updated["referral_required"] is False


def test_risk_assessor_keeps_benign_text_low_even_with_acoustic_support():
    state = {
        "session_id": "sess-voice-2",
        "chat_history": [{"role": "user", "content": "最近有点累，想听点舒缓音乐"}],
        "multimodal_features": {
            "voice_acoustic_features": {
                "pause_count": 3,
                "pause_total_ms": 1800,
                "pause_mean_ms": 600.0,
                "voiced_duration_ms": 1200,
                "speech_ratio": 0.4,
            }
        },
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {
            "emotion_keywords": [],
            "acoustic_observations": ["pause_total_ms_high", "speech_ratio_low"],
        },
        "reference_context": "",
        "risk_level": "low",
        "referral_required": False,
    }

    updated = risk_assessor_node(state, llm_client=DummyLowRiskLLM())

    assert updated["risk_level"] == "low"
    assert updated["referral_required"] is False
    assert updated["current_risk_score"] <= 0.35
    judgment = updated["agent_judgments"]["risk_assessor"]
    assert judgment["acoustic_support_level"] in {
        "mild",
        "notable",
    }
    assert judgment["base_score"] == 0.2
    assert judgment["adjusted_score"] == updated["current_risk_score"]
    assert judgment["used_acoustic_adjustment"] is True


def test_risk_assessor_uses_acoustic_support_only_as_medium_score_calibration():
    state = {
        "session_id": "sess-voice-3",
        "chat_history": [{"role": "user", "content": "最近很痛苦，也一直睡不好"}],
        "multimodal_features": {
            "voice_acoustic_features": {
                "pause_count": 4,
                "pause_total_ms": 2400,
                "pause_mean_ms": 600.0,
                "voiced_duration_ms": 1600,
                "speech_ratio": 0.38,
            }
        },
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {
            "emotion_keywords": ["痛苦", "失眠"],
            "acoustic_observations": ["pause_total_ms_high", "speech_ratio_low"],
        },
        "reference_context": "",
        "risk_level": "low",
        "referral_required": False,
    }

    updated = risk_assessor_node(state, llm_client=DummyLowRiskLLM())

    assert updated["risk_level"] == "medium"
    assert updated["referral_required"] is False
    assert updated["current_risk_score"] > 0.6
    assert updated["current_risk_score"] < 0.85
    judgment = updated["agent_judgments"]["risk_assessor"]
    assert judgment["acoustic_support_level"] in {
        "mild",
        "notable",
    }
    assert judgment["base_score"] == 0.6
    assert judgment["adjusted_score"] == updated["current_risk_score"]
    assert judgment["used_acoustic_adjustment"] is True


# ── Referral Agent Tests ──


def test_referral_agent_generates_hotline_card():
    state = {
        "session_id": "sess-high",
        "trace_id": "trace-1",
        "chat_history": [{"role": "user", "content": "我不想活了"}],
        "extracted_signals": {"emotion_keywords": ["不想活了"]},
        "risk_level": "high",
        "agent_judgments": {},
    }
    service = DummyAsyncAlertService()
    updated = asyncio.run(referral_agent_node(state, alert_service=service))
    assert updated["referral_required"] is True
    assert updated["hotline_card"] is not None
    assert "热线" in updated["hotline_card"]["hotline"]
    assert updated["alert_status"]["sent"] is True
    assert updated["agent_judgments"]["referral_agent"]["referral_triggered"] is True


def test_referral_agent_reply_is_warm_and_empathetic():
    state = {
        "session_id": "sess-high",
        "trace_id": "trace-1",
        "chat_history": [{"role": "user", "content": "我不想活了"}],
        "extracted_signals": {"emotion_keywords": ["不想活了"]},
        "risk_level": "high",
        "agent_judgments": {},
    }
    service = DummyAsyncAlertService()
    updated = asyncio.run(referral_agent_node(state, alert_service=service))
    # 检查温和话术关键标志
    assert "担心" in updated["reply"]
    assert "勇敢" in updated["reply"]


def test_referral_agent_redacts_session_id_in_alert():
    service = DummyAsyncAlertService()
    state = {
        "session_id": "session-abcdef123456",
        "trace_id": "trace-1",
        "chat_history": [{"role": "user", "content": "我不想活了"}],
        "extracted_signals": {"emotion_keywords": ["不想活了"]},
        "risk_level": "high",
        "agent_judgments": {},
    }
    asyncio.run(referral_agent_node(state, alert_service=service))
    assert service.payload is not None
    assert service.payload["session_id"] != "session-abcdef123456"


# ── Response Generator Tests ──


def test_response_generator_streams_reply_for_low_risk():
    llm = DummyStreamingLLM()
    state = {
        "session_id": "sess-1",
        "trace_id": "trace-1",
        "chat_history": [{"role": "user", "content": "有什么舒缓的音乐推荐？"}],
        "multimodal_features": {},
        "current_risk_score": 0.2,
        "agent_judgments": {},
        "extracted_signals": {"emotion_keywords": []},
        "risk_level": "low",
        "referral_required": False,
        "reference_context": "",
    }

    updated = asyncio.run(response_generator_node(state, llm_client=llm))

    assert updated["reply"]
    assert llm.complete_json_calls == 0
    assert llm.stream_prompts
    assert "仅返回 JSON" not in llm.stream_prompts[0][0]


def test_response_generator_uses_centralized_prompt_builders(monkeypatch):
    llm = DummyStreamingLLM()
    monkeypatch.setattr(
        "app.nodes.response_generator.build_response_generator_system_prompt",
        lambda: "response-system-sentinel",
        raising=False,
    )
    monkeypatch.setattr(
        "app.nodes.response_generator.build_response_generator_user_prompt",
        lambda *_args, **_kwargs: "response-user-sentinel",
        raising=False,
    )
    state = {
        "session_id": "sess-1",
        "trace_id": "trace-1",
        "chat_history": [{"role": "user", "content": "有什么舒缓的音乐推荐？"}],
        "multimodal_features": {},
        "current_risk_score": 0.2,
        "agent_judgments": {},
        "extracted_signals": {"emotion_keywords": []},
        "risk_level": "low",
        "referral_required": False,
        "reference_context": "",
    }

    asyncio.run(response_generator_node(state, llm_client=llm))

    assert llm.stream_prompts == [
        (
            "response-system-sentinel",
            "response-user-sentinel",
            "谢谢你愿意分享现在的感受。我会先陪你梳理一下，你最近最明显的情绪变化是什么？",
        )
    ]


def test_response_generator_uses_referral_reply_for_high_risk():
    state = {
        "session_id": "sess-1",
        "trace_id": "trace-1",
        "chat_history": [{"role": "user", "content": "我不想活了"}],
        "multimodal_features": {},
        "current_risk_score": 0.95,
        "agent_judgments": {},
        "extracted_signals": {"emotion_keywords": ["不想活了"]},
        "risk_level": "high",
        "referral_required": True,
        "reply": "我听到了你说的这些，也感受到你现在承受着很大的压力和痛苦。",
    }
    updated = asyncio.run(response_generator_node(state, llm_client=DummyStreamingLLM()))
    # Should use existing reply set by referral_agent
    assert "压力和痛苦" in updated["reply"]


def test_response_generator_falls_back_if_no_referral_reply():
    state = {
        "session_id": "sess-1",
        "trace_id": "trace-1",
        "chat_history": [{"role": "user", "content": "我不想活了"}],
        "multimodal_features": {},
        "current_risk_score": 0.95,
        "agent_judgments": {},
        "extracted_signals": {"emotion_keywords": ["不想活了"]},
        "risk_level": "high",
        "referral_required": True,
        "reply": "",
    }
    updated = asyncio.run(response_generator_node(state, llm_client=DummyStreamingLLM()))
    assert "辅导员" in updated["reply"]
    assert "热线" in updated["reply"]
