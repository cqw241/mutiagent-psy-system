"""信号聚合节点。

职责：
将 text_analyzer、voice_analyzer、face_analyzer 的独立输出
合并为统一的 extracted_signals，供下游 risk_assessor 消费。

这是 fan-out（多模态并行分析）之后的 fan-in 聚合点。
"""

from __future__ import annotations

from typing import Any

from app.utils.state_helpers import merge_agent_judgment


def signal_aggregator_node(state: dict[str, Any]) -> dict[str, Any]:
    """合并各 Analyzer Agent 的分析结果。"""

    text_signals = state.get("text_signals", {})
    voice_signals = state.get("voice_signals", {})
    face_signals = state.get("face_signals", {})

    # 聚合 extracted_signals
    extracted_signals: dict[str, Any] = {
        # 文本信号（核心）
        "emotion_keywords": text_signals.get("emotion_keywords", []),
        "sentiment": text_signals.get("sentiment", "unknown"),
        "observations": text_signals.get("observations", []),
        "multimodal_summary": text_signals.get("multimodal_summary", {}),
        # 声学信号（辅助）
        "acoustic_observations": voice_signals.get("acoustic_observations", []),
        # 面部信号（辅助）
        "facial_observations": face_signals.get("facial_observations", []),
        "dominant_blend": face_signals.get("dominant_blend", "unknown"),
        "dominant_confidence": face_signals.get("dominant_confidence", 0.0),
        "au_summary": face_signals.get("au_summary", {}),
    }

    # 记录聚合元信息
    sources_used = ["text_analyzer"]
    if voice_signals:
        sources_used.append("voice_analyzer")
    if face_signals:
        sources_used.append("face_analyzer")

    judgment = {
        "sources_used": sources_used,
        "text_signals_present": bool(text_signals),
        "voice_signals_present": bool(voice_signals),
        "face_signals_present": bool(face_signals),
    }

    return {
        "extracted_signals": extracted_signals,
        "agent_judgments": merge_agent_judgment(
            state, "signal_aggregator", judgment
        ),
    }
