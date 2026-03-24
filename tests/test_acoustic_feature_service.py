import asyncio

import numpy as np

from app.services.acoustic_feature_service import (
    AcousticFeatureExtractor,
    decode_audio_input,
)


def _sine_wave(frequency_hz: float, duration_ms: int, sample_rate: int = 16000) -> np.ndarray:
    sample_count = int(sample_rate * duration_ms / 1000)
    timeline = np.arange(sample_count, dtype=np.float32) / sample_rate
    waveform = 0.35 * np.sin(2 * np.pi * frequency_hz * timeline)
    return np.clip(waveform * 32767, -32768, 32767).astype(np.int16)


# ── Basic Physical Feature Tests (backward-compatible) ──


def test_extract_features_returns_structured_output_for_voiced_audio_with_pause():
    extractor = AcousticFeatureExtractor(sample_rate=16000, frame_duration_ms=30)
    audio = np.concatenate(
        [
            _sine_wave(180.0, 180),
            np.zeros(120 * 16, dtype=np.int16),
            _sine_wave(200.0, 180),
        ]
    )

    features = extractor.extract_features(audio)

    assert "pause_count" in features
    assert "energy_mean" in features
    assert "rms_mean" in features
    assert features["pause_count"] >= 1
    assert features["pause_total_ms"] > 0
    assert features["voiced_duration_ms"] > 0
    assert 0 < features["speech_ratio"] <= 1
    assert features["energy_mean"] > 0
    assert features["rms_mean"] > 0
    assert features["mean_f0"] is None or features["mean_f0"] > 50


def test_extract_features_handles_silence_and_short_audio_without_exception():
    extractor = AcousticFeatureExtractor(sample_rate=16000, frame_duration_ms=30)

    features = extractor.extract_features(np.zeros(160, dtype=np.int16))

    assert features["pause_count"] == 0
    assert features["pause_total_ms"] == 0
    assert features["pause_mean_ms"] == 0
    assert features["voiced_duration_ms"] == 0
    assert features["speech_ratio"] == 0
    assert features["mean_f0"] is None
    assert features["f0_std"] is None


def test_extract_features_degrades_safely_when_f0_estimation_fails(monkeypatch):
    extractor = AcousticFeatureExtractor(sample_rate=16000, frame_duration_ms=30)
    audio = _sine_wave(190.0, 240)

    def _raise_failure(_audio: np.ndarray) -> list[float]:
        raise RuntimeError("f0 failed")

    monkeypatch.setattr(extractor, "_estimate_f0_values", _raise_failure)

    features = extractor.extract_features(audio)

    assert features["mean_f0"] is None
    assert features["f0_std"] is None
    assert features["energy_mean"] > 0
    assert features["rms_mean"] > 0


# ── MFCC Tests ──


def test_extract_mfcc_returns_valid_statistics_for_normal_audio():
    extractor = AcousticFeatureExtractor(sample_rate=16000, n_mfcc=13)
    audio = _sine_wave(180.0, 500)  # 500ms sine wave
    float_audio = audio.astype(np.float32) / 32767.0

    mfcc = extractor.extract_mfcc(float_audio)

    assert mfcc["n_mfcc"] == 13
    assert mfcc["n_frames"] > 0
    assert len(mfcc["mfcc_mean"]) == 13
    assert len(mfcc["mfcc_std"]) == 13


def test_extract_mfcc_tensor_returns_correct_shape():
    extractor = AcousticFeatureExtractor(sample_rate=16000, n_mfcc=13)
    audio = _sine_wave(180.0, 500)
    float_audio = audio.astype(np.float32) / 32767.0

    tensor = extractor.extract_mfcc_tensor(float_audio)

    assert tensor is not None
    assert tensor.shape[0] == 13  # n_mfcc
    assert tensor.shape[1] > 0   # n_frames
    assert tensor.dtype == np.float32


def test_extract_mfcc_returns_empty_for_tiny_audio():
    extractor = AcousticFeatureExtractor(sample_rate=16000, n_mfcc=13, n_fft=512)
    tiny_audio = np.zeros(100, dtype=np.float32)  # less than n_fft

    mfcc = extractor.extract_mfcc(tiny_audio)

    assert mfcc["n_mfcc"] == 0
    assert mfcc["n_frames"] == 0


# ── Full Feature Vector Tests ──


def test_extract_full_feature_vector_has_correct_dimensionality():
    extractor = AcousticFeatureExtractor(sample_rate=16000, n_mfcc=13)
    audio = _sine_wave(180.0, 500)

    vec = extractor.extract_full_feature_vector(audio)

    assert vec is not None
    assert vec.shape == (9 + 2 * 13,)  # 35D
    assert vec.dtype == np.float32


def test_extract_full_feature_vector_returns_none_for_empty_audio():
    extractor = AcousticFeatureExtractor()
    vec = extractor.extract_full_feature_vector(np.array([], dtype=np.float32))
    assert vec is None


# ── Emotion Heuristic Tests ──


def test_emotion_heuristic_detects_depressed_low():
    extractor = AcousticFeatureExtractor()
    features = {
        "energy_mean": 0.001,
        "energy_std": 0.0002,
        "rms_mean": 0.01,
        "rms_std": 0.003,
        "mean_f0": 150.0,
        "f0_std": 8.0,       # very flat
        "speech_ratio": 0.35,
        "pause_count": 5,
        "pause_total_ms": 2500,
    }

    result = extractor.infer_emotion_heuristic(features)

    assert result.dominant_cue == "depressed_low"
    assert result.confidence >= 0.40


def test_emotion_heuristic_detects_anxious_agitated():
    extractor = AcousticFeatureExtractor()
    features = {
        "energy_mean": 0.05,
        "energy_std": 0.015,
        "rms_mean": 0.18,
        "rms_std": 0.04,
        "mean_f0": 280.0,
        "f0_std": 55.0,      # very volatile
        "speech_ratio": 0.85,
        "pause_count": 1,
        "pause_total_ms": 200,
    }

    result = extractor.infer_emotion_heuristic(features)

    assert result.dominant_cue == "anxious_agitated"
    assert result.confidence >= 0.40


def test_emotion_heuristic_returns_neutral_for_normal_features():
    extractor = AcousticFeatureExtractor()
    features = {
        "energy_mean": 0.01,
        "energy_std": 0.003,
        "rms_mean": 0.06,
        "rms_std": 0.015,
        "mean_f0": 180.0,
        "f0_std": 25.0,
        "speech_ratio": 0.65,
        "pause_count": 2,
        "pause_total_ms": 600,
    }

    result = extractor.infer_emotion_heuristic(features)

    assert result.dominant_cue == "neutral"


# ── Audio Input Decoder Tests ──


def test_decode_audio_input_handles_ndarray():
    audio = _sine_wave(180.0, 200)
    result, sr = decode_audio_input(audio)
    assert result is not None
    assert result.size > 0


def test_decode_audio_input_returns_none_for_none():
    result, sr = decode_audio_input(None)
    assert result is None
    assert sr == 0


def test_decode_audio_input_returns_none_for_invalid_base64():
    result, sr = decode_audio_input("not-valid-audio-file-path-either-xyzzy")
    assert result is None
    assert sr == 0
