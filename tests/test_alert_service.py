import asyncio

import httpx

from app.services.alert_service import AsyncWebhookAlertService, MockAlertService


def test_mock_alert_service_returns_success_result():
    service = MockAlertService()
    result = service.send_high_risk_alert({"session_id": "sess-1"})
    assert result["sent"] is True


def test_async_webhook_alert_service_masks_session_id():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = request.read().decode("utf-8")
        return httpx.Response(200, json={"ok": True})

    service = AsyncWebhookAlertService(
        webhook_url="http://localhost:8080/mock-webhook",
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(
        service.send_high_risk_alert_async(
            {
                "session_id": "session-abcdef123456",
                "risk_level": "high",
                "summary": "高风险摘要",
            }
        )
    )
    assert result["sent"] is True
    assert "session-abcdef123456" not in captured["json"]
