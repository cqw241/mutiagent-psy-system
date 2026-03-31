"""面部分析 Agent 节点。

职责：
1. 仅在前端传入面部特征数据时被路由触发
2. 从 face_segments 中提取 FACS 动作单元 (AU) 和情绪混合得分
3. 基于预设阈值规则，将 AU 强度映射为客观自然语言观察项
4. 不做诊断，不做情绪标签，只提供面部辅助观察项
5. 向下兼容旧的 multimodal_features.facial_data 通路
"""

from __future__ import annotations

import logging
from typing import Any

from app.utils.state_helpers import merge_agent_judgment

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# FACS AU 阈值规则表
# 格式: {AU_code: (threshold, observation_text)}
# 所有观测描述均为客观事实，不含诊断或情绪标签
# ──────────────────────────────────────────────────────────────

_AU_RULES: dict[str, tuple[float, str]] = {
    "AU01": (0.5, "内侧眉毛上提（眉头上扬）"),
    "AU02": (0.5, "外侧眉毛上提"),
    "AU04": (0.6, "用户持续皱眉（眉部紧缩）"),
    "AU05": (0.5, "上眼睑抬起（睁大眼睛）"),
    "AU06": (0.5, "面颊上提"),
    "AU07": (0.5, "眼睑收紧"),
    "AU09": (0.5, "鼻部皱缩"),
    "AU10": (0.5, "上唇提拉"),
    "AU12": (0.5, "嘴角上扬"),
    "AU15": (0.5, "嘴角明显下拉"),
    "AU17": (0.5, "下巴上推（撅嘴趋势）"),
    "AU20": (0.5, "嘴唇横向拉伸"),
    "AU23": (0.5, "嘴唇收紧"),
    "AU25": (0.6, "嘴唇分开"),
    "AU26": (0.5, "下颚张开"),
    "AU28": (0.5, "嘴唇向内卷缩"),
    "AU45": (0.6, "频繁眨眼"),
}

# 复合 AU 组合规则（更具语义的组合观察）
_COMPOUND_RULES: list[tuple[list[str], float, str]] = [
    (["AU01", "AU04"], 0.5, "眉部呈忧虑状态"),
    (["AU06", "AU12"], 0.5, "面部呈现微笑"),
    (["AU01", "AU02", "AU05", "AU26"], 0.4, "面部呈现惊讶状态"),
    (["AU04", "AU07"], 0.5, "眉部及眼部持续紧绷"),
    (["AU15", "AU17"], 0.5, "嘴角下拉伴随下巴收紧"),
]

# 旧版面部表情到辅助观察项的映射（向下兼容）
_EMOTION_OBSERVATION_MAP: dict[str, str] = {
    "sad": "facial_expression_sad",
    "angry": "facial_expression_angry",
    "fearful": "facial_expression_fearful",
    "disgusted": "facial_expression_disgusted",
    "surprised": "facial_expression_surprised",
    "neutral": "facial_expression_neutral",
    "happy": "facial_expression_happy",
}


def _evaluate_au_rules(action_units: dict[str, float]) -> list[str]:
    """对单个 face_segment 的 AU 值应用阈值规则，返回触发的观察项列表。"""

    observations: list[str] = []

    # 单 AU 规则
    for au_code, (threshold, obs_text) in _AU_RULES.items():
        value = action_units.get(au_code, 0.0)
        if value > threshold:
            observations.append(obs_text)

    # 复合 AU 规则
    for au_group, threshold, obs_text in _COMPOUND_RULES:
        values = [action_units.get(au, 0.0) for au in au_group]
        if all(v > threshold for v in values):
            # 避免与单 AU 规则重复
            if obs_text not in observations:
                observations.append(obs_text)

    return observations


def _extract_dominant_blend(blend_scores: dict[str, float]) -> tuple[str, float]:
    """从情绪混合得分中提取主导情绪及其置信度。"""

    if not blend_scores:
        return "unknown", 0.0

    dominant = max(blend_scores, key=blend_scores.get)  # type: ignore[arg-type]
    return dominant, blend_scores[dominant]


def _build_au_summary(action_units: dict[str, float]) -> dict[str, float]:
    """构建超阈值 AU 摘要字典（仅包含 > 0 的 AU）。"""

    return {k: v for k, v in action_units.items() if v > 0}


def face_analyzer_node(state: dict[str, Any]) -> dict[str, Any]:
    """提取面部特征中的风险辅助线索。

    优先从 face_segments（前端 1–1.5s 聚合快照）提取：
    1. 对最新 segment 的 action_units 应用阈值规则 → 客观观察项
    2. 从 blend_scores 提取主导情绪（仅作辅助上下文，不作为独立判断依据）
    3. 若无 face_segments，回退到旧的 multimodal_features.facial_data 通路
    """

    face_segments: list[dict[str, Any]] = state.get("face_segments", [])
    facial_observations: list[str] = []
    dominant_blend: str = "unknown"
    dominant_confidence: float = 0.0
    au_summary: dict[str, float] = {}
    feature_source: str = "none"

    if face_segments:
        # 使用最新的面部特征快照
        latest = face_segments[-1]
        action_units = latest.get("action_units", {})
        blend_scores = latest.get("blend_scores", {})

        facial_observations = _evaluate_au_rules(action_units)
        dominant_blend, dominant_confidence = _extract_dominant_blend(blend_scores)
        au_summary = _build_au_summary(action_units)
        feature_source = "face_segments"

        logger.debug(
            "Face analyzer: %d observations from %d AUs, dominant_blend=%s(%.2f)",
            len(facial_observations),
            len(action_units),
            dominant_blend,
            dominant_confidence,
        )
    else:
        # 向下兼容：旧的 multimodal_features.facial_data 通路
        multimodal = state.get("multimodal_features", {})
        facial_data = multimodal.get("facial_data", {})
        facial_emotion = (
            facial_data.get("emotion")
            or multimodal.get("facial_emotion", "")
        )

        if facial_emotion:
            obs = _EMOTION_OBSERVATION_MAP.get(
                facial_emotion.lower(),
                f"facial_expression_{facial_emotion.lower()}",
            )
            facial_observations.append(obs)
            dominant_blend = facial_emotion.lower()
            feature_source = "legacy_multimodal"

    face_signals: dict[str, Any] = {
        "facial_observations": facial_observations,
        "dominant_blend": dominant_blend,
        "dominant_confidence": dominant_confidence,
        "au_summary": au_summary,
        "segment_count": len(face_segments),
    }

    judgment: dict[str, Any] = {
        "has_face_data": bool(face_segments) or feature_source == "legacy_multimodal",
        "feature_source": feature_source,
        "facial_observations": facial_observations,
        "dominant_blend": dominant_blend,
        "dominant_confidence": dominant_confidence,
        "segment_count": len(face_segments),
    }

    return {
        "face_signals": face_signals,
        "agent_judgments": merge_agent_judgment(state, "face_analyzer", judgment),
    }
