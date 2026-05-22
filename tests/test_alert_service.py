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


def test_async_webhook_alert_service_preserves_alert_event_id():
    service = AsyncWebhookAlertService(webhook_url="mock://counselor-alert")

    payload = service.sanitize_payload(
        {
            "alert_event_id": "alert_123",
            "session_id": "session-abcdefghij",
            "masked_session_id": "session-masked1234",
            "risk_level": "high",
            "summary": "高风险摘要",
        }
    )

    assert payload["alert_event_id"] == "alert_123"
    assert payload["session_id"] == "session-masked1234"
    assert payload["session_id"] != "session-abcdefghij"


def test_async_webhook_alert_service_keeps_alert_event_id_and_masked_session():
    service = AsyncWebhookAlertService(webhook_url="mock://counselor-alert")
    masked_session_id = service.mask_session_id("session-abcdef123456")

    result = service.send_high_risk_alert(
        {
            "alert_event_id": "alert_123",
            "session_id": masked_session_id,
            "risk_level": "high",
            "summary": "高风险摘要",
        }
    )

    assert result["payload_preview"]["alert_event_id"] == "alert_123"
    assert result["payload_preview"]["session_id"] == masked_session_id


def test_async_webhook_alert_service_treats_mock_url_as_success():
    service = AsyncWebhookAlertService(webhook_url="mock://counselor-alert")

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
    assert result["channel"] == "mock_webhook"
    assert result["payload_preview"]["session_id"] != "session-abcdef123456"
