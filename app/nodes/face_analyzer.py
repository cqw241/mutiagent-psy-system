"""面部分析 Agent 节点。

职责：
1. 仅在前端传入面部特征数据时被路由触发
2. 当前为占位实现，提取 facial_emotion 等 JSON 字段
3. 预留 LLM 调用接口，便于未来接入视频理解模型
4. 不做诊断，不做情绪标签，只提供面部辅助观察项
"""

from __future__ import annotations

from typing import Any

from app.utils.state_helpers import merge_agent_judgment

# 面部表情到辅助观察项的映射（占位规则，后续可接模型）
_EMOTION_OBSERVATION_MAP: dict[str, str] = {
    "sad": "facial_expression_sad",
    "angry": "facial_expression_angry",
    "fearful": "facial_expression_fearful",
    "disgusted": "facial_expression_disgusted",
    "surprised": "facial_expression_surprised",
    "neutral": "facial_expression_neutral",
    "happy": "facial_expression_happy",
}


def face_analyzer_node(state: dict[str, Any]) -> dict[str, Any]:
    """提取面部特征中的风险辅助线索。"""

    multimodal = state.get("multimodal_features", {})
    facial_data = multimodal.get("facial_data", {})
    facial_emotion = (
        facial_data.get("emotion")
        or multimodal.get("facial_emotion", "")
    )

    facial_observations: list[str] = []
    if facial_emotion:
        obs = _EMOTION_OBSERVATION_MAP.get(
            facial_emotion.lower(), f"facial_expression_{facial_emotion.lower()}"
        )
        facial_observations.append(obs)

    face_signals = {
        "facial_observations": facial_observations,
        "facial_emotion": facial_emotion or "unknown",
        "raw_facial_data": facial_data,
    }

    judgment = {
        "has_face_data": True,
        "facial_emotion": facial_emotion or "unknown",
        "facial_observations": facial_observations,
    }

    return {
        "face_signals": face_signals,
        "agent_judgments": merge_agent_judgment(state, "face_analyzer", judgment),
    }
