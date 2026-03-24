"""emotion2vec 本地推理服务。

目标：
1. 仅作为现有语音分析链路的可选增强信号，不替代传统声学特征。
2. 优先使用本地已下载模型目录，避免运行时网络依赖。
3. 所有失败路径都结构化返回，绝不向上抛出未处理异常。
"""

from __future__ import annotations

import logging
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import numpy as np

from app.core.config import Settings, get_settings
from app.services.acoustic_feature_service import decode_audio_input

try:
    import soundfile as sf
except ImportError:  # pragma: no cover
    sf = None


logger = logging.getLogger(__name__)

EMOTION2VEC_SOURCE = "emotion2vec_plus_large"
_OBSERVATION_BY_LABEL = {
    "angry": "语音情绪分类更接近 angry，需结合文本和上下文综合判断。",
    "disgusted": "语音情绪分类更接近 disgusted，需结合文本和上下文综合判断。",
    "fearful": "语音情绪分类更接近 fearful，需结合文本和上下文综合判断。",
    "happy": "语音情绪分类更接近 happy，需结合文本和上下文综合判断。",
    "neutral": "语音情绪分类更接近 neutral，可作为辅助语音信号参考。",
    "other": "语音情绪分类更接近 other，建议结合文本和上下文综合判断。",
    "sad": "语音情绪分类更接近 sad，建议结合文本和上下文综合判断。",
    "surprised": "语音情绪分类更接近 surprised，建议结合文本和上下文综合判断。",
    "unknown": "语音情绪分类结果不明确，可作为辅助语音信号参考。",
}

PipelineFactory = Callable[[str], Callable[..., Any]]


def build_emotion2vec_reading(
    *,
    status: str,
    model_dir: str | None = None,
    emotion_label: str | None = None,
    confidence: float | None = None,
    topk: list[dict[str, Any]] | None = None,
    observation: str | None = None,
    raw_output: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "source": EMOTION2VEC_SOURCE,
        "model_dir": model_dir,
        "emotion_label": emotion_label,
        "confidence": confidence,
        "topk": topk,
        "observation": observation,
        "raw_output": raw_output,
        "error": error,
    }


class Emotion2VecService:
    """使用本地 modelscope emotion-recognition pipeline 的包装服务。"""

    def __init__(
        self,
        settings: Settings | None = None,
        pipeline_factory: PipelineFactory | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model_dir = self.settings.emotion2vec_model_dir.strip() or None
        self.pipeline_factory = pipeline_factory or self._default_pipeline_factory
        self._pipeline: Callable[..., Any] | None = None

    def analyze(self, audio_input: Any) -> dict[str, Any]:
        """对单段原始音频做 utterance 级别 emotion2vec 推理。"""

        if not self.settings.enable_emotion2vec:
            return build_emotion2vec_reading(
                status="disabled",
                model_dir=self.model_dir,
            )

        if not self.model_dir:
            return build_emotion2vec_reading(
                status="unavailable",
                error="EMOTION2VEC_MODEL_DIR is not configured.",
            )

        model_path = Path(self.model_dir)
        if not model_path.exists():
            return build_emotion2vec_reading(
                status="unavailable",
                model_dir=str(model_path),
                error=f"Model directory not found: {model_path}",
            )

        audio, sample_rate = decode_audio_input(
            audio_input,
            target_sr=self.settings.emotion2vec_sample_rate,
        )
        if audio is None or audio.size == 0:
            return build_emotion2vec_reading(
                status="unavailable",
                model_dir=str(model_path),
                error="Valid raw audio is required for emotion2vec inference.",
            )

        if sf is None:
            return build_emotion2vec_reading(
                status="unavailable",
                model_dir=str(model_path),
                error="soundfile is required for emotion2vec inference.",
            )

        try:
            pipeline = self._get_pipeline()
        except Exception as exc:
            logger.warning("Emotion2Vec pipeline unavailable: %s", exc)
            return build_emotion2vec_reading(
                status="unavailable",
                model_dir=str(model_path),
                error=str(exc),
            )

        temp_audio_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                temp_audio_path = Path(handle.name)
            sf.write(str(temp_audio_path), np.asarray(audio, dtype=np.float32), sample_rate)
            raw_output = pipeline(
                str(temp_audio_path),
                granularity="utterance",
                extract_embedding=False,
            )
            normalized = self._normalize_output(raw_output)
            if normalized is None:
                return build_emotion2vec_reading(
                    status="error",
                    model_dir=str(model_path),
                    raw_output=self._raw_output_dict(raw_output),
                    error="Unexpected emotion2vec output format.",
                )
            return normalized | {
                "status": "ok",
                "source": EMOTION2VEC_SOURCE,
                "model_dir": str(model_path),
                "raw_output": self._raw_output_dict(raw_output),
                "error": None,
            }
        except Exception as exc:
            logger.warning("Emotion2Vec inference failed: %s", exc)
            return build_emotion2vec_reading(
                status="error",
                model_dir=str(model_path),
                error=str(exc),
            )
        finally:
            if temp_audio_path is not None:
                try:
                    temp_audio_path.unlink(missing_ok=True)
                except Exception:
                    logger.debug("Failed to delete temporary emotion2vec audio file.")

    def _get_pipeline(self) -> Callable[..., Any]:
        if self._pipeline is None:
            if self.model_dir is None:
                raise RuntimeError("EMOTION2VEC_MODEL_DIR is not configured.")
            self._pipeline = self.pipeline_factory(self.model_dir)
        return self._pipeline

    @staticmethod
    def _default_pipeline_factory(model_dir: str) -> Callable[..., Any]:
        try:
            from modelscope.pipelines import pipeline
            from modelscope.utils.constant import Tasks
        except ImportError as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError(
                "ModelScope emotion-recognition dependencies are unavailable. "
                "Install `modelscope`, `datasets`, `simplejson`, "
                "`sortedcontainers`, `addict`, `funasr`, `torch`, "
                "`pillow`, and `torchaudio`."
            ) from exc

        return pipeline(task=Tasks.emotion_recognition, model=model_dir)

    @staticmethod
    def _raw_output_dict(raw_output: Any) -> dict[str, Any] | None:
        if raw_output is None:
            return None
        if isinstance(raw_output, dict):
            return raw_output
        if isinstance(raw_output, list):
            return {"results": raw_output}
        return {"value": raw_output}

    @classmethod
    def _normalize_output(cls, raw_output: Any) -> dict[str, Any] | None:
        if isinstance(raw_output, list):
            if not raw_output or not isinstance(raw_output[0], dict):
                return None
            raw_output = raw_output[0]
        if not isinstance(raw_output, dict):
            return None

        labels = raw_output.get("labels")
        scores = raw_output.get("scores")
        if not isinstance(labels, list) or not isinstance(scores, list):
            return None

        topk = [
            {
                "label": cls._normalize_label(label),
                "score": round(float(score), 4),
            }
            for label, score in zip(labels, scores, strict=False)
        ]
        topk = [item for item in topk if item["label"]]
        if not topk:
            return None

        topk.sort(key=lambda item: item["score"], reverse=True)
        top1 = topk[0]
        label = top1["label"]
        confidence = top1["score"]
        observation = _OBSERVATION_BY_LABEL.get(
            label,
            f"语音情绪分类更接近 {label}，建议结合文本和上下文综合判断。",
        )
        return {
            "emotion_label": label,
            "confidence": confidence,
            "topk": topk,
            "observation": observation,
        }

    @staticmethod
    def _normalize_label(label: Any) -> str:
        normalized = str(label).strip().lower()
        if "/" in normalized:
            normalized = normalized.rsplit("/", 1)[-1]
        if normalized == "<unk>":
            return "unknown"
        return normalized


@lru_cache(maxsize=8)
def get_emotion2vec_service(settings: Settings | None = None) -> Emotion2VecService:
    """按配置缓存 emotion2vec 服务实例，避免重复加载大模型。"""

    resolved_settings = settings or get_settings()
    return Emotion2VecService(resolved_settings)
