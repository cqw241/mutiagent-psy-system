from pathlib import Path
import builtins

import numpy as np
import pytest

from app.core.config import Settings
from app.services.emotion2vec_service import Emotion2VecService


def _make_audio() -> np.ndarray:
    sr = 16000
    t = np.arange(int(sr * 0.3), dtype=np.float32) / sr
    return (0.25 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_emotion2vec_service_returns_disabled_when_feature_off(tmp_path):
    service = Emotion2VecService(
        Settings(
            enable_emotion2vec=False,
            emotion2vec_model_dir=str(tmp_path),
        )
    )

    result = service.analyze(_make_audio())

    assert result["status"] == "disabled"
    assert result["emotion_label"] is None
    assert result["topk"] is None


def test_emotion2vec_service_returns_unavailable_for_missing_model_dir(tmp_path):
    missing_dir = tmp_path / "missing-model"
    service = Emotion2VecService(
        Settings(
            enable_emotion2vec=True,
            emotion2vec_model_dir=str(missing_dir),
        )
    )

    result = service.analyze(_make_audio())

    assert result["status"] == "unavailable"
    assert result["model_dir"] == str(missing_dir)
    assert result["error"]


def test_emotion2vec_service_returns_structured_result_on_success(tmp_path):
    model_dir = tmp_path / "emotion2vec"
    model_dir.mkdir()

    seen_inputs: list[str] = []

    def fake_pipeline_factory(resolved_model_dir: str):
        assert resolved_model_dir == str(model_dir)

        def infer(audio_path: str, granularity: str, extract_embedding: bool):
            seen_inputs.append(audio_path)
            assert Path(audio_path).exists()
            assert granularity == "utterance"
            assert extract_embedding is False
            return {
                "labels": ["sad", "neutral", "angry"],
                "scores": [0.72, 0.2, 0.08],
            }

        return infer

    service = Emotion2VecService(
        Settings(
            enable_emotion2vec=True,
            emotion2vec_model_dir=str(model_dir),
        ),
        pipeline_factory=fake_pipeline_factory,
    )

    result = service.analyze(_make_audio())

    assert seen_inputs
    assert result["status"] == "ok"
    assert result["source"] == "emotion2vec_plus_large"
    assert result["model_dir"] == str(model_dir)
    assert result["emotion_label"] == "sad"
    assert result["confidence"] == 0.72
    assert result["topk"][0] == {"label": "sad", "score": 0.72}
    assert "sad" in result["observation"]
    assert result["raw_output"]["labels"][0] == "sad"


def test_emotion2vec_service_returns_error_when_inference_raises(tmp_path):
    model_dir = tmp_path / "emotion2vec"
    model_dir.mkdir()

    def fake_pipeline_factory(_: str):
        def infer(*args, **kwargs):
            raise RuntimeError("inference failed")

        return infer

    service = Emotion2VecService(
        Settings(
            enable_emotion2vec=True,
            emotion2vec_model_dir=str(model_dir),
        ),
        pipeline_factory=fake_pipeline_factory,
    )

    result = service.analyze(_make_audio())

    assert result["status"] == "error"
    assert result["emotion_label"] is None
    assert result["error"] == "inference failed"


def test_emotion2vec_service_normalizes_modelscope_list_output(tmp_path):
    model_dir = tmp_path / "emotion2vec"
    model_dir.mkdir()

    def fake_pipeline_factory(_: str):
        def infer(*args, **kwargs):
            return [
                {
                    "key": "seg-1",
                    "labels": ["难过/sad", "中立/neutral", "生气/angry"],
                    "scores": [0.77, 0.18, 0.05],
                }
            ]

        return infer

    service = Emotion2VecService(
        Settings(
            enable_emotion2vec=True,
            emotion2vec_model_dir=str(model_dir),
        ),
        pipeline_factory=fake_pipeline_factory,
    )

    result = service.analyze(_make_audio())

    assert result["status"] == "ok"
    assert result["emotion_label"] == "sad"
    assert result["topk"][0] == {"label": "sad", "score": 0.77}


def test_emotion2vec_service_install_guidance_mentions_full_runtime_stack(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"modelscope.pipelines", "modelscope.utils.constant"}:
            raise ImportError("missing modelscope stack")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError) as exc_info:
        Emotion2VecService._default_pipeline_factory("/tmp/emotion2vec")

    message = str(exc_info.value)
    for dependency in [
        "modelscope",
        "datasets",
        "simplejson",
        "sortedcontainers",
        "addict",
        "funasr",
        "torch",
        "pillow",
        "torchaudio",
    ]:
        assert dependency in message
