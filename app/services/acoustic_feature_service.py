"""实时语音链路的声学特征提取。

本模块做"工程化特征提取"——物理声学特征 + MFCC + 启发式情绪线索。
设计目标：
1. 依赖 numpy + librosa，CPU 可稳定运行
2. 短片段、静音、低质量输入时安全降级
3. 输出稳定的结构化字典；MFCC 同时提供原始 ndarray 接口，为 A40 SER 模型预留张量输入
4. 不输出诊断/医学结论，只提供声学观察项

扩展预留：
- `extract_mfcc_tensor()` 返回 (n_mfcc, T) 标准化 ndarray，可直接转 torch.Tensor
- `extract_full_feature_vector()` 返回拼接后的定长特征向量，对齐 emotion2vec 等 SER 输入
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ── 可选依赖：librosa / soundfile ──
try:
    import librosa
except ImportError:  # pragma: no cover
    librosa = None

try:
    import soundfile as sf
except ImportError:  # pragma: no cover
    sf = None


# ────────────────────────────────────────────────────────────────────
# Data Classes
# ────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class AcousticFeatureSet:
    """基础物理声学特征集。"""

    pause_count: int = 0
    pause_total_ms: int = 0
    pause_mean_ms: float = 0.0
    voiced_duration_ms: int = 0
    speech_ratio: float = 0.0
    mean_f0: float | None = None
    f0_std: float | None = None
    energy_mean: float = 0.0
    energy_std: float = 0.0
    rms_mean: float = 0.0
    rms_std: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MFCCFeatureSet:
    """MFCC 特征集——为 SER 模型预留的标准化输入。"""

    mfcc_mean: list[float] = field(default_factory=list)
    mfcc_std: list[float] = field(default_factory=list)
    n_mfcc: int = 0
    n_frames: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EmotionHeuristic:
    """启发式情绪推断——基于声学特征的规则映射。

    emotion_cues 列表中的每一项格式为: (线索代码, 置信度 0~1)
    这些不是诊断标签，是风险辅助线索。
    """

    emotion_cues: list[tuple[str, float]] = field(default_factory=list)
    dominant_cue: str = "neutral"
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "emotion_cues": [
                {"cue": cue, "confidence": round(conf, 3)}
                for cue, conf in self.emotion_cues
            ],
            "dominant_cue": self.dominant_cue,
            "confidence": round(self.confidence, 3),
        }


# ────────────────────────────────────────────────────────────────────
# Audio Input Parsing
# ────────────────────────────────────────────────────────────────────


def decode_audio_input(
    raw_input: Any,
    target_sr: int = 16000,
) -> tuple[np.ndarray | None, int]:
    """从多种来源安全解析音频到 float32 ndarray。

    支持：
    - np.ndarray 直传（PCM int16 或 float32）
    - base64 编码字符串（内含 WAV / FLAC / OGG 等 soundfile 支持的格式）
    - 文件路径字符串

    Returns:
        (audio_float32, sample_rate) 或 (None, 0) 表示解析失败。
    """

    if raw_input is None:
        return None, 0

    # ── ndarray 直传 ──
    if isinstance(raw_input, np.ndarray):
        audio = _normalize_pcm(raw_input)
        return (audio, target_sr) if audio.size > 0 else (None, 0)

    # ── bytes / base64 字符串 ──
    if isinstance(raw_input, (bytes, str)):
        audio_bytes: bytes | None = None
        if isinstance(raw_input, str):
            # 尝试 base64 解码，失败则当文件路径
            try:
                audio_bytes = base64.b64decode(raw_input, validate=True)
            except Exception:
                return _load_audio_file(raw_input, target_sr)
        else:
            audio_bytes = raw_input

        if audio_bytes and sf is not None:
            try:
                audio, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
                audio = np.asarray(audio, dtype=np.float32)
                if audio.ndim == 2:
                    audio = audio.mean(axis=1)
                if sr != target_sr and librosa is not None:
                    audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)
                    sr = target_sr
                return audio, sr
            except Exception as exc:
                logger.warning("Failed to decode audio bytes: %s", exc)
                return None, 0

    return None, 0


def _load_audio_file(file_path: str, target_sr: int) -> tuple[np.ndarray | None, int]:
    """用 librosa / soundfile 加载音频文件。"""

    if librosa is not None:
        try:
            audio, sr = librosa.load(file_path, sr=target_sr, mono=True)
            return audio.astype(np.float32), sr
        except Exception as exc:
            logger.warning("Failed to load audio file with librosa: %s", exc)
            return None, 0

    if sf is not None:
        try:
            audio, sr = sf.read(file_path, dtype="float32")
            audio = np.asarray(audio, dtype=np.float32)
            if audio.ndim == 2:
                audio = audio.mean(axis=1)
            return audio, sr
        except Exception as exc:
            logger.warning("Failed to load audio file with soundfile: %s", exc)
            return None, 0

    return None, 0


def _normalize_pcm(audio_pcm: np.ndarray) -> np.ndarray:
    """将 int16 / int32 PCM 或 float 数组归一化到 [-1, 1] float32。"""

    audio = np.asarray(audio_pcm)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if audio.ndim != 1 or audio.size == 0:
        return np.array([], dtype=np.float32)

    if np.issubdtype(audio.dtype, np.integer):
        scale = float(max(abs(np.iinfo(audio.dtype).min), np.iinfo(audio.dtype).max) or 1)
        normalized = audio.astype(np.float32) / scale
    else:
        normalized = audio.astype(np.float32)

    return np.ascontiguousarray(np.clip(normalized, -1.0, 1.0))


# ────────────────────────────────────────────────────────────────────
# Core Feature Extractor
# ────────────────────────────────────────────────────────────────────


class AcousticFeatureExtractor:
    """基于单通道 PCM 的声学特征提取器。

    支持基础物理特征（F0/RMS/Pause）和 MFCC 提取。
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        min_f0_hz: float = 70.0,
        max_f0_hz: float = 350.0,
        min_required_f0_frames: int = 2,
        n_mfcc: int = 13,
        n_fft: int = 512,
        hop_length: int = 160,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_size = max(1, int(sample_rate * frame_duration_ms / 1000))
        self.min_f0_hz = min_f0_hz
        self.max_f0_hz = max_f0_hz
        self.min_required_f0_frames = min_required_f0_frames
        # MFCC 参数
        self.n_mfcc = n_mfcc
        self.n_fft = n_fft
        self.hop_length = hop_length

    # ── 基础物理特征（保持完全向后兼容） ──

    def extract_features(
        self,
        audio_pcm: np.ndarray,
        *,
        pause_durations_ms: list[int] | None = None,
        voiced_duration_ms: int | None = None,
        segment_duration_ms: int | None = None,
    ) -> dict[str, Any]:
        normalized = self._prepare_audio(audio_pcm)
        if normalized.size == 0:
            return AcousticFeatureSet().to_dict()

        frames = self._frame_audio(normalized)
        if frames.size == 0:
            return AcousticFeatureSet().to_dict()

        energy_values = np.mean(np.square(frames), axis=1)
        rms_values = np.sqrt(np.maximum(energy_values, 0.0))
        voiced_mask = self._build_voiced_mask(rms_values)

        if pause_durations_ms is None:
            pause_durations_ms = self._estimate_pause_durations_ms(voiced_mask)

        if voiced_duration_ms is None:
            voiced_duration_ms = int(voiced_mask.sum() * self.frame_duration_ms)

        if segment_duration_ms is None:
            segment_duration_ms = int(round(normalized.shape[0] * 1000 / self.sample_rate))

        pause_total_ms = int(sum(pause_durations_ms))
        pause_count = len(pause_durations_ms)
        pause_mean_ms = round(pause_total_ms / pause_count, 3) if pause_count else 0.0
        speech_ratio = (
            round(voiced_duration_ms / segment_duration_ms, 4)
            if segment_duration_ms > 0
            else 0.0
        )

        mean_f0, f0_std = self._safe_f0_stats(normalized, voiced_mask)

        return AcousticFeatureSet(
            pause_count=pause_count,
            pause_total_ms=pause_total_ms,
            pause_mean_ms=pause_mean_ms,
            voiced_duration_ms=max(0, int(voiced_duration_ms)),
            speech_ratio=max(0.0, min(1.0, speech_ratio)),
            mean_f0=mean_f0,
            f0_std=f0_std,
            energy_mean=round(float(np.mean(energy_values)), 6),
            energy_std=round(float(np.std(energy_values)), 6),
            rms_mean=round(float(np.mean(rms_values)), 6),
            rms_std=round(float(np.std(rms_values)), 6),
        ).to_dict()

    # ── MFCC 特征 ──

    def extract_mfcc(self, audio_float32: np.ndarray) -> dict[str, Any]:
        """提取 MFCC 统计特征（均值 + 标准差）。"""

        tensor = self.extract_mfcc_tensor(audio_float32)
        if tensor is None:
            return MFCCFeatureSet().to_dict()

        return MFCCFeatureSet(
            mfcc_mean=[round(float(v), 6) for v in tensor.mean(axis=1)],
            mfcc_std=[round(float(v), 6) for v in tensor.std(axis=1)],
            n_mfcc=tensor.shape[0],
            n_frames=tensor.shape[1],
        ).to_dict()

    def extract_mfcc_tensor(self, audio_float32: np.ndarray) -> np.ndarray | None:
        """提取 MFCC 原始张量 (n_mfcc, T)。

        返回标准化后的 ndarray，可直接转 torch.Tensor 送入 SER 模型。
        如果 librosa 不可用或音频太短，返回 None。
        """

        if librosa is None:
            logger.debug("librosa not available, skipping MFCC extraction")
            return None

        audio = self._prepare_audio(audio_float32)
        if audio.size < self.n_fft:
            return None

        try:
            mfcc = librosa.feature.mfcc(
                y=audio,
                sr=self.sample_rate,
                n_mfcc=self.n_mfcc,
                n_fft=self.n_fft,
                hop_length=self.hop_length,
            )
            return mfcc.astype(np.float32)
        except Exception as exc:
            logger.warning("MFCC extraction failed: %s", exc)
            return None

    # ── 复合特征向量（为 SER 模型预留） ──

    def extract_full_feature_vector(
        self,
        audio_pcm: np.ndarray,
    ) -> np.ndarray | None:
        """提取拼接后的定长特征向量。

        布局：[物理特征(9D) | MFCC均值(n_mfcc) | MFCC标准差(n_mfcc)]
        总维度：9 + 2 * n_mfcc（默认 9 + 26 = 35D）

        可直接作为 emotion2vec / SER 模型的辅助输入特征，
        或用于传统 ML 分类器（SVM/XGBoost）的特征空间。
        """

        normalized = self._prepare_audio(audio_pcm)
        if normalized.size == 0:
            return None

        phys = self.extract_features(audio_pcm)
        physical_vec = np.array([
            float(phys.get("speech_ratio", 0)),
            float(phys.get("mean_f0") or 0),
            float(phys.get("f0_std") or 0),
            float(phys.get("energy_mean", 0)),
            float(phys.get("energy_std", 0)),
            float(phys.get("rms_mean", 0)),
            float(phys.get("rms_std", 0)),
            float(phys.get("pause_count", 0)),
            float(phys.get("pause_mean_ms", 0)),
        ], dtype=np.float32)

        mfcc_data = self.extract_mfcc(normalized)
        mfcc_mean = np.array(mfcc_data.get("mfcc_mean") or [0.0] * self.n_mfcc, dtype=np.float32)
        mfcc_std = np.array(mfcc_data.get("mfcc_std") or [0.0] * self.n_mfcc, dtype=np.float32)

        return np.concatenate([physical_vec, mfcc_mean, mfcc_std])

    # ── 启发式情绪推断 ──

    def infer_emotion_heuristic(
        self,
        features: dict[str, Any],
        mfcc_features: dict[str, Any] | None = None,
    ) -> EmotionHeuristic:
        """基于物理声学特征的启发式情绪线索推断。

        映射规则（不是诊断）：
        - 低能量 + F0平缓 + 大量停顿 → depressed_low（抑郁/低落线索）
        - 极高能量 + F0剧烈波动     → anxious_agitated（焦虑/激动线索）
        - 高 F0 + 高能量              → stressed_tense（紧张线索）
        - 正常范围                     → neutral
        """

        cues: list[tuple[str, float]] = []

        energy_mean = float(features.get("energy_mean", 0))
        energy_std = float(features.get("energy_std", 0))
        rms_mean = float(features.get("rms_mean", 0))
        mean_f0 = features.get("mean_f0")
        f0_std = features.get("f0_std")
        speech_ratio = float(features.get("speech_ratio", 0))
        pause_count = int(features.get("pause_count", 0))
        pause_total_ms = float(features.get("pause_total_ms", 0))

        # ── 抑郁/低落线索：低能量 + F0平缓 + 大量停顿 ──
        low_energy = energy_mean < 0.003 or rms_mean < 0.025
        flat_f0 = (mean_f0 is not None and f0_std is not None and f0_std < 15.0)
        many_pauses = pause_count >= 3 or pause_total_ms >= 1500
        low_speech = speech_ratio > 0 and speech_ratio < 0.45

        depressed_score = 0.0
        if low_energy:
            depressed_score += 0.30
        if flat_f0:
            depressed_score += 0.25
        if many_pauses:
            depressed_score += 0.25
        if low_speech:
            depressed_score += 0.20
        if depressed_score >= 0.40:
            cues.append(("depressed_low", min(depressed_score, 0.95)))

        # ── 焦虑/激动线索：高能量 + F0剧烈波动 ──
        high_energy = energy_mean > 0.02 or rms_mean > 0.12
        volatile_f0 = (mean_f0 is not None and f0_std is not None and f0_std > 40.0)
        high_speech = speech_ratio > 0.80

        anxious_score = 0.0
        if high_energy:
            anxious_score += 0.30
        if volatile_f0:
            anxious_score += 0.40
        if high_speech:
            anxious_score += 0.15
        if energy_std > 0.008:
            anxious_score += 0.15
        if anxious_score >= 0.40:
            cues.append(("anxious_agitated", min(anxious_score, 0.95)))

        # ── 紧张线索：高 F0 + 中高能量 ──
        high_f0 = mean_f0 is not None and mean_f0 > 250.0
        if high_f0 and (high_energy or energy_mean > 0.01):
            stressed_conf = 0.50 + (0.15 if energy_std > 0.005 else 0.0)
            cues.append(("stressed_tense", min(stressed_conf, 0.85)))

        # ── MFCC 辅助：第 1 个 MFCC 系数异常低说明整体能量偏低 ──
        if mfcc_features and mfcc_features.get("mfcc_mean"):
            mfcc1 = mfcc_features["mfcc_mean"][0] if mfcc_features["mfcc_mean"] else 0
            if mfcc1 < -200:
                existing = [c for c, _ in cues]
                if "depressed_low" not in existing:
                    cues.append(("depressed_low", 0.35))

        if not cues:
            return EmotionHeuristic(
                emotion_cues=[("neutral", 0.6)],
                dominant_cue="neutral",
                confidence=0.6,
            )

        cues.sort(key=lambda x: x[1], reverse=True)
        dominant = cues[0]
        return EmotionHeuristic(
            emotion_cues=cues,
            dominant_cue=dominant[0],
            confidence=dominant[1],
        )

    # ── 内部工具方法（保持向后兼容） ──

    @staticmethod
    def _prepare_audio(audio_pcm: np.ndarray) -> np.ndarray:
        return _normalize_pcm(audio_pcm)

    def _frame_audio(self, normalized_audio: np.ndarray) -> np.ndarray:
        if normalized_audio.size < self.frame_size:
            pad_width = self.frame_size - normalized_audio.size
            normalized_audio = np.pad(normalized_audio, (0, pad_width))

        frame_count = normalized_audio.size // self.frame_size
        if frame_count <= 0:
            return np.empty((0, self.frame_size), dtype=np.float32)

        trimmed = normalized_audio[: frame_count * self.frame_size]
        return trimmed.reshape(frame_count, self.frame_size)

    @staticmethod
    def _build_voiced_mask(rms_values: np.ndarray) -> np.ndarray:
        if rms_values.size == 0:
            return np.zeros(0, dtype=bool)

        peak_rms = float(np.max(rms_values))
        if peak_rms <= 1e-5:
            return np.zeros(rms_values.shape[0], dtype=bool)

        threshold = max(0.015, peak_rms * 0.35)
        return rms_values >= threshold

    def _estimate_pause_durations_ms(self, voiced_mask: np.ndarray) -> list[int]:
        if voiced_mask.size == 0 or not np.any(voiced_mask):
            return []

        first_voiced = int(np.argmax(voiced_mask))
        last_voiced = int(voiced_mask.size - np.argmax(voiced_mask[::-1]) - 1)
        if last_voiced <= first_voiced:
            return []

        pauses: list[int] = []
        current_pause_frames = 0
        for is_voiced in voiced_mask[first_voiced : last_voiced + 1]:
            if is_voiced:
                if current_pause_frames:
                    pauses.append(current_pause_frames * self.frame_duration_ms)
                    current_pause_frames = 0
                continue
            current_pause_frames += 1
        return pauses

    def _safe_f0_stats(
        self,
        normalized_audio: np.ndarray,
        voiced_mask: np.ndarray,
    ) -> tuple[float | None, float | None]:
        try:
            f0_values = self._estimate_f0_values(normalized_audio, voiced_mask)
        except Exception as exc:
            logger.warning("F0 extraction failed, fallback to null. reason=%s", exc)
            return None, None

        if len(f0_values) < self.min_required_f0_frames:
            return None, None

        return (
            round(float(np.mean(f0_values)), 3),
            round(float(np.std(f0_values)), 3),
        )

    def _estimate_f0_values(
        self,
        normalized_audio: np.ndarray,
        voiced_mask: np.ndarray,
    ) -> list[float]:
        frames = self._frame_audio(normalized_audio)
        if frames.size == 0 or voiced_mask.size == 0:
            return []

        min_lag = max(1, int(self.sample_rate / self.max_f0_hz))
        max_lag = max(min_lag + 1, int(self.sample_rate / self.min_f0_hz))

        f0_values: list[float] = []
        for frame, is_voiced in zip(frames, voiced_mask, strict=False):
            if not is_voiced:
                continue

            centered = frame - np.mean(frame)
            frame_energy = float(np.sum(centered * centered))
            if frame_energy <= 1e-6:
                continue

            windowed = centered * np.hamming(centered.size)
            autocorr = np.correlate(windowed, windowed, mode="full")[windowed.size - 1 :]
            if autocorr.size <= min_lag:
                continue

            search_end = min(max_lag, autocorr.size)
            lag_window = autocorr[min_lag:search_end]
            if lag_window.size == 0:
                continue

            best_offset = int(np.argmax(lag_window))
            best_lag = min_lag + best_offset
            peak_value = float(lag_window[best_offset])
            normalized_peak = peak_value / max(float(autocorr[0]), 1e-9)
            if normalized_peak < 0.3:
                continue

            f0_values.append(self.sample_rate / best_lag)

        return f0_values
