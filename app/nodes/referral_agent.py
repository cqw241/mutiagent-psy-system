"""转介辅助 Agent 节点。

职责：
1. 仅在 risk_level == "high" 时被条件路由触发
2. 生成温和的转介过渡话术（不是冰冷的模板弹窗）
3. 构建 hotline_card 援助卡片
4. 触发辅导员 webhook 告警（脱敏后）
5. 设置 referral_required 标志

设计原则：
- 话术必须体现同理心和安全感
- 不能让学生感觉自己正在被"系统审查"
- 过渡语应自然，像一位关心你的朋友
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.services.alert_service import (
    AsyncWebhookAlertService,
    BaseAlertService,
)
from app.services.alert_event_store import FileAlertEventStore
from app.utils.state_helpers import latest_user_message, merge_agent_judgment


# 温和过渡话术模板（替代原来冰冷的转介模板）
_WARM_TRANSITION_TEMPLATE = (
    "我听到了你说的这些，也感受到你现在承受着很大的压力和痛苦。"
    "你愿意告诉我这些，我觉得这本身就很勇敢。\n\n"
    "不过，我有些担心你提到的这些感受。"
    "我希望能有更专业的人来陪伴你度过这段时间。"
    "下面是一些可以随时联系的支持资源，他们都非常温暖和专业——"
)


def _build_hotline_card() -> dict[str, Any]:
    """构建援助热线卡片。"""

    return {
        "title": "温暖支持提示",
        "hotline": "学校心理咨询中心 24 小时热线：400-xxx-xxxx",
        "tips": [
            "尽量不要独处，联系同学、家人或辅导员陪伴你。",
            "如果存在立即伤害自己的风险，请直接联系当地急救资源。",
        ],
    }


def _build_high_risk_summary(state: dict[str, Any]) -> dict[str, Any]:
    """构建发送给辅导员的告警摘要。"""

    keywords = state.get("extracted_signals", {}).get("emotion_keywords", [])
    return {
        "session_id": state.get("session_id", ""),
        "risk_level": "high",
        "summary": "检测到需要人工关注的高风险心理支持对话，请尽快复核。",
        "trace_id": state.get("trace_id", ""),
        "keywords": keywords[:5],
    }


async def referral_agent_node(
    state: dict[str, Any],
    alert_service: BaseAlertService | None = None,
    alert_event_store: FileAlertEventStore | None = None,
) -> dict[str, Any]:
    """高风险转介处理。

    生成温和过渡话术 + 热线卡片 + 触发辅导员告警。
    """

    settings = get_settings()
    alerts = alert_service or AsyncWebhookAlertService(
        webhook_url=settings.counselor_alert_webhook
    )
    event_store = alert_event_store or FileAlertEventStore()

    # 构建热线卡片
    hotline_card = _build_hotline_card()

    summary_payload = _build_high_risk_summary(state)
    event = event_store.create(
        session_id=state.get("session_id", ""),
        trace_id=state.get("trace_id", ""),
        risk_level="high",
        latest_risk_evidence={
            "keywords": summary_payload.get("keywords", []),
            "extracted_signals": state.get("extracted_signals", {}),
        },
        summary=summary_payload["summary"],
    )

    # 触发告警（同步 + 异步双保险）
    payload = {
        **summary_payload,
        "alert_event_id": event.alert_event_id,
        "session_id": event.masked_session_id,
        "masked_session_id": event.masked_session_id,
    }
    scheduled_status = alerts.send_high_risk_alert(payload)
    try:
        alert_status = await alerts.send_high_risk_alert_async(payload)
    except Exception:
        alert_status = {**scheduled_status, "sent": False}
    delivery_status = "delivered" if alert_status.get("sent") else "delivery_failed"
    event = event_store.update(event.alert_event_id, delivery_status=delivery_status)
    alert_status = {
        **alert_status,
        "alert_event_id": event.alert_event_id,
        "delivery_status": event.delivery_status,
        "handler_status": event.handler_status,
        "masked_session_id": event.masked_session_id,
    }

    # 温和过渡话术作为 referral_preamble，供 response_generator 组装最终回复
    judgment = {
        "referral_triggered": True,
        "alert_sent": bool(alert_status.get("sent")),
        "hotline_card_generated": True,
    }

    return {
        "referral_required": True,
        "hotline_card": hotline_card,
        "alert_event_id": event.alert_event_id,
        "alert_status": alert_status,
        "reply": _WARM_TRANSITION_TEMPLATE,
        "agent_judgments": merge_agent_judgment(state, "referral_agent", judgment),
    }
