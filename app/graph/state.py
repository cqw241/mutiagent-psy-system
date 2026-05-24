"""LangGraph 全局状态定义。

StateGraph 的核心价值不是"把函数串起来"，而是把所有节点共享的上下文显式化。
多智能体架构下，每个 Analyzer Agent 有独立的输出槽，
signal_aggregator 负责 fan-in 合并，risk_assessor 从聚合结果中消费。
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, TypedDict

from app.models.schemas import RiskLevel


def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """字典合并 reducer。

    用于 fan-out 场景下多个并行节点各自写入不同 key 到同一个 dict channel。
    浅合并：right 的 key 覆盖 left 的同名 key。
    """

    merged = dict(left)
    merged.update(right)
    return merged


class PsychologyGraphState(TypedDict, total=False):
    """多智能体共享状态。

    字段分组：
    - 会话上下文：session_id, trace_id, user_profile, chat_history
    - 多模态原始输入：multimodal_features, voice_segments, face_segments
    - 模态路由标志：has_voice, has_face
    - Analyzer 独立输出槽：text_signals, voice_signals, face_signals
    - 聚合信号：extracted_signals（由 signal_aggregator fan-in 生成）
    - RAG：reference_context
    - 风险评估：current_risk_score, risk_level, referral_required
    - 转介与回复：hotline_card, alert_event_id, alert_status, reply
    - 可解释性：agent_judgments, trace
    """

    # ── 会话上下文 ──
    session_id: str
    trace_id: str
    user_profile: dict[str, Any]
    chat_history: Annotated[list[dict[str, str]], add]

    # ── 多模态原始输入 ──
    multimodal_features: dict[str, Any]
    voice_segments: Annotated[list[dict[str, Any]], add]
    face_segments: Annotated[list[dict[str, Any]], add]

    # ── 模态路由标志（用于 conditional edge） ──
    has_voice: bool
    has_face: bool

    # ── Analyzer Agent 独立输出槽 ──
    text_signals: dict[str, Any]
    voice_signals: dict[str, Any]
    face_signals: dict[str, Any]

    # ── 聚合信号（signal_aggregator 输出） ──
    extracted_signals: dict[str, Any]

    # ── RAG ──
    reference_context: str
    peer_support_context: str

    # ── 风险评估 ──
    current_risk_score: float
    risk_level: RiskLevel
    referral_required: bool

    # ── 转介与回复 ──
    hotline_card: dict[str, Any] | None
    alert_event_id: str | None
    alert_status: dict[str, Any]
    reply: str

    # ── 可解释性与审计 ──
    # 使用 merge_dicts reducer，允许 fan-out 中多个并行节点各写自己的 key
    agent_judgments: Annotated[dict[str, Any], merge_dicts]
    trace: dict[str, Any]
