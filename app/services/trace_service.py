"""审计与前端调试用 trace 组装逻辑。"""

from __future__ import annotations

from typing import Any


def build_trace_payload(state: dict[str, Any]) -> dict[str, Any]:
    extracted_signals = state.get("extracted_signals", {})
    agent_judgments = state.get("agent_judgments", {})
    multimodal_features = state.get("multimodal_features", {})
    risk_judgment = agent_judgments.get("risk_assessor", {})
    voice_judgment = agent_judgments.get("voice_analyzer", {})
    face_judgment = agent_judgments.get("face_analyzer", {})
    emotion2vec_reading = state.get("voice_signals", {}).get("emotion2vec_reading", {})
    face_signals = state.get("face_signals", {})

    latest_voice_segment = multimodal_features.get("latest_voice_segment")
    acoustic_observations = extracted_signals.get("acoustic_observations", [])
    acoustic_support_level = risk_judgment.get("acoustic_support_level", "none")

    base_score = risk_judgment.get(
        "base_score",
        state.get("current_risk_score", 0.0),
    )
    adjusted_score = risk_judgment.get(
        "adjusted_score",
        state.get("current_risk_score", 0.0),
    )
    risk_level = risk_judgment.get("final_risk_level", state.get("risk_level", "low"))

    return {
        "latest_voice_segment": latest_voice_segment,
        "acoustic_observations": acoustic_observations,
        "acoustic_support_level": acoustic_support_level,
        "emotion2vec": {
            "enabled": voice_judgment.get("emotion2vec_enabled", False),
            "used": voice_judgment.get("emotion2vec_used", False),
            "status": voice_judgment.get(
                "emotion2vec_status",
                emotion2vec_reading.get("status", "unknown"),
            ),
            "label": voice_judgment.get(
                "emotion2vec_label",
                emotion2vec_reading.get("emotion_label"),
            ),
            "confidence": emotion2vec_reading.get("confidence"),
            "model_dir": emotion2vec_reading.get("model_dir"),
            "error": emotion2vec_reading.get("error"),
        },
        "face_analysis": {
            "facial_observations": face_signals.get("facial_observations", []),
            "dominant_blend": face_signals.get(
                "dominant_blend",
                face_judgment.get("dominant_blend", "unknown"),
            ),
            "dominant_confidence": face_signals.get(
                "dominant_confidence",
                face_judgment.get("dominant_confidence", 0.0),
            ),
            "segment_count": face_signals.get(
                "segment_count",
                face_judgment.get("segment_count", 0),
            ),
            "feature_source": face_judgment.get("feature_source", "none"),
        },
        "risk_calibration": {
            "base_score": base_score,
            "adjusted_score": adjusted_score,
            "risk_level": risk_level,
            "used_acoustic_adjustment": risk_judgment.get(
                "used_acoustic_adjustment",
                False,
            ),
        },
        "agent_judgments": agent_judgments,
    }
