"""Pydantic 请求/响应模型。

这里把接口契约提前结构化，避免前后端联调时出现“靠 prompt 推断字段”的问题。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high"]
MessageRole = Literal["user", "assistant", "system"]


class ChatMessage(BaseModel):
    """会话中的一条消息。"""

    role: MessageRole
    content: str


class HotlineCard(BaseModel):
    """高风险时返回给前端的援助卡片。

    Task 1 不接真实资源中心，只返回一个可稳定渲染的占位结构。
    """

    title: str
    hotline: str
    tips: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    """`/chat` 输入模型。

    采用工程版接口：既兼顾前端联调，也为后续接入用户画像和多模态数据预留位置。
    """

    session_id: str = Field(..., description="前端会话 ID")
    message: str = Field(..., description="用户本轮输入文本")
    multimodal_features: dict[str, Any] = Field(
        default_factory=dict, description="前端传入的多模态特征，例如面部情绪 JSON"
    )
    user_profile: dict[str, Any] = Field(
        default_factory=dict, description="可选用户画像，不包含敏感持久化逻辑"
    )


class ChatResponse(BaseModel):
    """`/chat` 输出模型。"""

    reply: str
    risk_level: RiskLevel
    referral_required: bool
    agent_judgments: dict[str, Any] = Field(default_factory=dict)
    extracted_signals: dict[str, Any] = Field(default_factory=dict)
    trace_id: str
    trace: dict[str, Any] = Field(default_factory=dict)
    hotline_card: HotlineCard | None = None
    alert_status: dict[str, Any] = Field(default_factory=dict)


class CounselorAlertPayload(BaseModel):
    """发送给辅导员告警系统的数据负载。"""

    session_id: str
    risk_level: RiskLevel
    summary: str
    trace_id: str
    extracted_signals: dict[str, Any] = Field(default_factory=dict)
