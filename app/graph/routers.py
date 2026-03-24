"""LangGraph 条件路由函数。

集中管理所有条件边（Conditional Edge）的路由逻辑：
- modality_router：基于输入模态 fan-out 到对应 Analyzer Agent
- risk_router：基于 risk_level 决定是否走 referral_agent
"""

from __future__ import annotations

from typing import Any


def modality_router(state: dict[str, Any]) -> list[str]:
    """基于可用模态，fan-out 到对应 Analyzer 节点。

    - text_analyzer 始终触发（文本是基础模态）
    - voice_analyzer 仅在 has_voice=True 时触发
    - face_analyzer 仅在 has_face=True 时触发

    返回 list[str] 以启用 LangGraph 多目标并行执行。
    """

    targets = ["text_analyzer"]

    if state.get("has_voice"):
        targets.append("voice_analyzer")

    if state.get("has_face"):
        targets.append("face_analyzer")

    return targets


def risk_router(state: dict[str, Any]) -> str:
    """基于风险评估结果，决定是否进入转介分支。

    - high → referral_agent（生成热线卡片 + 触发告警）
    - low/medium → 直接到 response_generator
    """

    if state.get("risk_level") == "high":
        return "referral_agent"
    return "response_generator"
