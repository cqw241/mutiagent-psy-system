"""高风险转介告警服务。

Task 1 只做 mock，但接口要稳定，后续换成真实 webhook 或校内系统时不改业务节点。
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Any

import httpx


class BaseAlertService(ABC):
    """告警服务抽象。"""

    @abstractmethod
    def send_high_risk_alert(self, payload: dict[str, Any]) -> dict[str, Any]:
        """发送高风险告警。"""

    @abstractmethod
    async def send_high_risk_alert_async(self, payload: dict[str, Any]) -> dict[str, Any]:
        """异步发送高风险告警。"""


class MockAlertService(BaseAlertService):
    """本地 mock 实现。

    不做真实网络调用，返回稳定结构用于测试和联调。
    """

    def send_high_risk_alert(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "sent": True,
            "channel": "mock_webhook",
            "target": "counselor",
            "payload_preview": payload,
        }

    async def send_high_risk_alert_async(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.send_high_risk_alert(payload)


class AsyncWebhookAlertService(BaseAlertService):
    """面向 mock/真实 webhook 的异步告警实现。"""

    def __init__(
        self,
        webhook_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.webhook_url = webhook_url
        self.transport = transport

    @staticmethod
    def mask_session_id(session_id: str) -> str:
        if session_id.startswith("session-") and len(session_id) == len("session-") + 10:
            return session_id
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        return f"session-{digest[:10]}"

    def sanitize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        masked_session_id = payload.get("masked_session_id") or self.mask_session_id(
            payload.get("session_id", "")
        )
        return {
            "alert_event_id": payload.get("alert_event_id", ""),
            "session_id": masked_session_id,
            "risk_level": payload.get("risk_level", "high"),
            "summary": payload.get("summary", ""),
            "trace_id": payload.get("trace_id", ""),
            "keywords": payload.get("keywords", []),
        }

    def send_high_risk_alert(self, payload: dict[str, Any]) -> dict[str, Any]:
        safe_payload = self.sanitize_payload(payload)
        if self.webhook_url.startswith("mock://"):
            return {
                "sent": True,
                "channel": "mock_webhook",
                "payload_preview": safe_payload,
            }
        return {
            "sent": True,
            "channel": "webhook_scheduled",
            "payload_preview": safe_payload,
        }

    async def send_high_risk_alert_async(self, payload: dict[str, Any]) -> dict[str, Any]:
        safe_payload = self.sanitize_payload(payload)
        if self.webhook_url.startswith("mock://"):
            return {
                "sent": True,
                "channel": "mock_webhook",
                "payload_preview": safe_payload,
            }
        try:
            async with httpx.AsyncClient(timeout=5, transport=self.transport) as client:
                response = await client.post(self.webhook_url, json=safe_payload)
                response.raise_for_status()
            return {"sent": True, "channel": "webhook", "payload_preview": safe_payload}
        except Exception:
            return {"sent": False, "channel": "webhook", "payload_preview": safe_payload}
