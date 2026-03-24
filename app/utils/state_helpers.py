"""Graph 状态操作公共工具。

将各节点中重复出现的状态读取/合并逻辑集中在此，遵循 DRY 原则。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4


def latest_user_message(state: dict[str, Any]) -> str:
    """从 chat_history 中获取最近一条用户消息。"""

    for message in reversed(state.get("chat_history", [])):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


def merge_agent_judgment(
    state: dict[str, Any], agent_name: str, judgment: dict[str, Any]
) -> dict[str, Any]:
    """安全合并单个 Agent 的判断结果到 agent_judgments。

    返回合并后的完整 agent_judgments dict，不修改原 state。
    """

    agent_judgments = dict(state.get("agent_judgments", {}))
    agent_judgments[agent_name] = judgment
    return agent_judgments


def build_initial_state(
    *,
    session_id: str,
    message: str,
    user_profile: dict | None = None,
    multimodal_features: dict | None = None,
    voice_segments: list[dict] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """构建 LangGraph 初始 state，REST 与 WebSocket 共用。"""

    mm_features = multimodal_features or {}
    segments = voice_segments or []

    return {
        "session_id": session_id,
        "trace_id": trace_id or f"trace-{uuid4().hex}",
        "user_profile": user_profile or {},
        "chat_history": [{"role": "user", "content": message}],
        "multimodal_features": mm_features,
        "voice_segments": segments,
        "has_voice": bool(segments),
        "has_face": bool(mm_features.get("facial_data")),
        "trace": {},
        "current_risk_score": 0.0,
        "extracted_signals": {},
        "text_signals": {},
        "voice_signals": {},
        "face_signals": {},
        "reference_context": "",
        "risk_level": "low",
        "referral_required": False,
        "agent_judgments": {},
        "reply": "",
        "hotline_card": None,
        "alert_status": {},
    }
