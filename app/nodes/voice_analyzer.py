"""语音分析 Agent 节点。

完整的 Audio-to-Emotion Pipeline：
1. 输入解析：从 State 安全获取音频数据（ndarray / base64 / 文件路径）
2. 物理特征提取：F0 / RMS / Pause（CPU 运算，asyncio.to_thread 非阻塞）
3. MFCC 提取：librosa 梅尔频率倒谱系数，为 SER 模型预留张量接口
4. 启发式情绪推断：低能量+F0平缓+停顿→抑郁线索；高能量+F0波动→焦虑线索
5. LLM 语义判读：将声学特征字典交给 Qwen 做快速情绪语义解读
6. 状态写入：结构化 JSON 写入 voice_signals + agent_judgments

工程约束：
- 非阻塞：CPU 密集特征提取通过 asyncio.to_thread 执行
- 优雅降级：音频损坏/格式不支持时返回 degraded 状态
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

from app.core.config import get_settings
from app.services.acoustic_feature_service import (
    AcousticFeatureExtractor,
    decode_audio_input,
)
from app.services.acoustic_fusion_service import extract_acoustic_observations
from app.services.emotion2vec_service import (
    build_emotion2vec_reading,
    get_emotion2vec_service,
)
from app.services.llm_client import BaseLLMClient, LiteLLMClient
from app.utils.state_helpers import latest_user_message, merge_agent_judgment

logger = logging.getLogger(__name__)

# 共享提取器实例（线程安全，无可变状态）
_extractor = AcousticFeatureExtractor()

# 降级响应模板
_DEGRADED_VOICE_SIGNALS: dict[str, Any] = {
    "status": "degraded",
    "confidence": 0,
    "features": None,
    "acoustic_observations": [],
    "mfcc_features": None,
    "emotion_heuristic": None,
    "llm_emotion_reading": None,
}


def _build_emotion2vec_judgment(
    settings: Any,
    emotion2vec_reading: dict[str, Any],
) -> dict[str, Any]:
    return {
        "emotion2vec_enabled": bool(settings.enable_emotion2vec),
        "emotion2vec_used": emotion2vec_reading.get("status") == "ok",
        "emotion2vec_status": emotion2vec_reading.get("status"),
        "emotion2vec_label": emotion2vec_reading.get("emotion_label"),
    }


def _build_emotion2vec_no_audio_reading(settings: Any) -> dict[str, Any]:
    if not settings.enable_emotion2vec:
        return build_emotion2vec_reading(
            status="disabled",
            model_dir=settings.emotion2vec_model_dir or None,
        )

    return build_emotion2vec_reading(
        status="unavailable",
        model_dir=settings.emotion2vec_model_dir or None,
        error="Raw audio unavailable for emotion2vec inference.",
    )


async def _run_emotion2vec_analysis(
    settings: Any,
    audio: np.ndarray,
) -> dict[str, Any]:
    try:
        service = get_emotion2vec_service(settings)
        return await asyncio.to_thread(service.analyze, audio)
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.warning("Emotion2Vec analysis failed unexpectedly: %s", exc)
        return build_emotion2vec_reading(
            status="error",
            model_dir=settings.emotion2vec_model_dir or None,
            error=str(exc),
        )


def _resolve_audio_data(state: dict[str, Any]) -> np.ndarray | None:
    """从 State 中多路径解析音频数据。

    优先级：
    1. voice_segments[-1].audio_pcm（实时 WebSocket 流）
    2. multimodal_features.audio_data（base64 或文件路径）
    3. multimodal_features.audio_pcm（ndarray 直传）
    """

    # 方式 1：voice_segments 中的 PCM 数据
    voice_segments = state.get("voice_segments", [])
    if voice_segments:
        latest_segment = voice_segments[-1]
        audio_pcm = latest_segment.get("audio_pcm")
        if audio_pcm is not None:
            if isinstance(audio_pcm, np.ndarray):
                return audio_pcm
            audio, _ = decode_audio_input(audio_pcm)
            if audio is not None:
                return audio

    # 方式 2：multimodal_features 中的音频
    multimodal = state.get("multimodal_features", {})

    audio_data = multimodal.get("audio_data")
    if audio_data is not None:
        audio, _ = decode_audio_input(audio_data)
        if audio is not None:
            return audio

    audio_pcm = multimodal.get("audio_pcm")
    if audio_pcm is not None and isinstance(audio_pcm, np.ndarray):
        return audio_pcm

    return None


def _extract_all_features(audio: np.ndarray) -> dict[str, Any]:
    """CPU 密集：提取物理特征 + MFCC + 启发式情绪——在 to_thread 中执行。"""

    physical_features = _extractor.extract_features(audio)
    mfcc_features = _extractor.extract_mfcc(audio)
    emotion_heuristic = _extractor.infer_emotion_heuristic(
        physical_features, mfcc_features
    )

    return {
        "physical_features": physical_features,
        "mfcc_features": mfcc_features,
        "emotion_heuristic": emotion_heuristic.to_dict(),
    }


def _build_llm_prompt(
    features: dict[str, Any],
    user_text: str,
    emotion_heuristic: dict[str, Any],
) -> tuple[str, str]:
    """构建给 LLM 的声学情绪语义判读提示词。"""

    system_prompt = (
        "你是一位高校心理风险识别系统中的语音分析辅助节点。"
        "你将收到结构化的声学特征数据和启发式情绪推断结果。"
        "请基于这些数据，用 1-2 句极简的中文对用户当前的语音情绪状态做一个"
        "中性、客观的情绪观察（注意：不是诊断，不是治疗建议）。"
        "同时给出一个 emotion_label（只能是 neutral / low_mood / anxious / "
        "agitated / stressed / flat_affect 之一）和一个 confidence（0~1）。"
        "仅返回 JSON，格式：{\"observation\": str, \"emotion_label\": str, \"confidence\": float}"
    )

    user_prompt = (
        f"声学物理特征：{features.get('physical_features', {})}\n"
        f"MFCC 统计：n_mfcc={features.get('mfcc_features', {}).get('n_mfcc', 0)}, "
        f"帧数={features.get('mfcc_features', {}).get('n_frames', 0)}\n"
        f"启发式情绪推断：{emotion_heuristic}\n"
        f"用户文本（如有）：{user_text or '无文本输入'}\n"
        "请给出你的情绪观察。"
    )

    return system_prompt, user_prompt


def _fallback_from_segment_features(state: dict[str, Any]) -> dict[str, Any]:
    """当无 raw audio 但 voice_segments 中有预提取特征时，回退处理。"""

    voice_segments = state.get("voice_segments", [])
    multimodal = state.get("multimodal_features", {})

    acoustic_features: dict[str, Any] = {}
    if voice_segments:
        latest_segment = voice_segments[-1]
        segment_features = latest_segment.get("acoustic_features", {})
        if segment_features:
            acoustic_features = segment_features

    if not acoustic_features:
        acoustic_features = multimodal.get("voice_acoustic_features", {})

    if not acoustic_features:
        return _DEGRADED_VOICE_SIGNALS.copy()

    acoustic_observations = extract_acoustic_observations(acoustic_features)
    emotion_heuristic = _extractor.infer_emotion_heuristic(acoustic_features)

    return {
        "status": "ok_from_precomputed",
        "confidence": 0.6,
        "features": acoustic_features,
        "acoustic_observations": acoustic_observations,
        "mfcc_features": None,
        "emotion_heuristic": emotion_heuristic.to_dict(),
        "llm_emotion_reading": None,
        "segment_count": len(voice_segments),
    }


async def voice_analyzer_node(
    state: dict[str, Any],
    llm_client: BaseLLMClient | None = None,
) -> dict[str, Any]:
    """语音分析 Agent：特征提取 → 启发式推断 → LLM 语义判读。"""

    settings = get_settings()
    user_text = latest_user_message(state)

    # ── Step 1: 尝试解析 raw audio ──
    audio = _resolve_audio_data(state)

    if audio is None or audio.size == 0:
        # 没有原始音频，尝试从预计算特征回退
        voice_signals = _fallback_from_segment_features(state)
        emotion2vec_reading = _build_emotion2vec_no_audio_reading(settings)
        voice_signals["emotion2vec_reading"] = emotion2vec_reading
        judgment = {
            "has_voice_data": bool(voice_signals.get("features")),
            "status": voice_signals.get("status", "degraded"),
            "feature_source": "precomputed_segment" if voice_signals.get("features") else "none",
            "acoustic_observations": voice_signals.get("acoustic_observations", []),
            "emotion_heuristic": voice_signals.get("emotion_heuristic"),
        }
        judgment.update(_build_emotion2vec_judgment(settings, emotion2vec_reading))
        return {
            "voice_signals": voice_signals,
            "agent_judgments": merge_agent_judgment(state, "voice_analyzer", judgment),
        }

    # ── Step 2: CPU 密集特征提取（非阻塞） ──
    try:
        all_features = await asyncio.to_thread(_extract_all_features, audio)
    except Exception as exc:
        logger.warning("Voice feature extraction failed: %s", exc)
        degraded = _DEGRADED_VOICE_SIGNALS.copy()
        degraded["error"] = str(exc)
        emotion2vec_reading = await _run_emotion2vec_analysis(settings, audio)
        degraded["emotion2vec_reading"] = emotion2vec_reading
        judgment = {
            "has_voice_data": True,
            "status": "degraded",
            "error": str(exc),
        }
        judgment.update(_build_emotion2vec_judgment(settings, emotion2vec_reading))
        return {
            "voice_signals": degraded,
            "agent_judgments": merge_agent_judgment(state, "voice_analyzer", judgment),
        }

    physical_features = all_features["physical_features"]
    mfcc_features = all_features["mfcc_features"]
    emotion_heuristic = all_features["emotion_heuristic"]

    # ── Step 3: 声学观察项（规则化） ──
    acoustic_observations = extract_acoustic_observations(physical_features)

    # ── Step 4: LLM 语义判读（可选，失败不阻断） ──
    llm_emotion_reading: dict[str, Any] | None = None
    try:
        llm = llm_client or LiteLLMClient(get_settings())
        sys_prompt, usr_prompt = _build_llm_prompt(
            all_features, user_text, emotion_heuristic
        )
        llm_result = llm.complete_json(sys_prompt, usr_prompt)
        if llm_result and llm_result.get("emotion_label"):
            llm_emotion_reading = llm_result
    except Exception as exc:
        logger.warning("LLM emotion reading failed (non-blocking): %s", exc)

    # ── Step 5: emotion2vec 深度 SER（可选，失败不阻断） ──
    emotion2vec_reading = await _run_emotion2vec_analysis(settings, audio)

    # ── Step 6: 组装 voice_signals ──
    voice_signals: dict[str, Any] = {
        "status": "ok",
        "confidence": emotion_heuristic.get("confidence", 0.5),
        "features": physical_features,
        "acoustic_observations": acoustic_observations,
        "mfcc_features": mfcc_features,
        "emotion_heuristic": emotion_heuristic,
        "llm_emotion_reading": llm_emotion_reading,
        "emotion2vec_reading": emotion2vec_reading,
        "segment_count": len(state.get("voice_segments", [])),
    }

    judgment = {
        "has_voice_data": True,
        "status": "ok",
        "feature_source": "raw_audio",
        "acoustic_observations": acoustic_observations,
        "emotion_heuristic": emotion_heuristic,
        "llm_emotion_used": llm_emotion_reading is not None,
        "mfcc_extracted": bool(mfcc_features and mfcc_features.get("n_mfcc")),
    }
    judgment.update(_build_emotion2vec_judgment(settings, emotion2vec_reading))

    return {
        "voice_signals": voice_signals,
        "agent_judgments": merge_agent_judgment(state, "voice_analyzer", judgment),
    }
