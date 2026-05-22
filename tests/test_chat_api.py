from fastapi.testclient import TestClient

from app.api.routes.chat import compiled_graph
from app.core.config import get_settings
from app.main import app


def test_chat_endpoint_returns_structured_response():
    client = TestClient(app)
    response = client.post(
        "/chat",
        json={
            "session_id": "sess-1",
            "message": "最近压力很大，睡不着",
            "multimodal_features": {"facial_emotion": "sad"},
            "user_profile": {"school": "demo-university"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "reply" in body
    assert "risk_level" in body
    assert "trace_id" in body
    assert "trace" in body
    assert body["trace"]["risk_calibration"]["risk_level"] == body["risk_level"]
    assert "acoustic_support_level" in body["trace"]


def test_chat_endpoint_returns_referral_for_high_risk_input(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COUNSELOR_ALERT_WEBHOOK", "mock://counselor-alert")
    get_settings.cache_clear()
    client = TestClient(app)
    response = client.post(
        "/chat",
        json={
            "session_id": "sess-2",
            "message": "我不想活了",
            "multimodal_features": {"facial_emotion": "despair"},
            "user_profile": {"school": "demo-university"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["risk_level"] == "high"
    assert body["referral_required"] is True
    assert body["alert_status"]["sent"] is True
    assert body["alert_status"]["alert_event_id"].startswith("alert_")
    assert body["alert_status"]["delivery_status"] == "delivered"
    assert body["alert_status"]["handler_status"] == "created"
    get_settings.cache_clear()


def test_chat_endpoint_uses_session_memory():
    client = TestClient(app)
    session_id = "sess-memory-api"
    client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "这是第一轮",
            "multimodal_features": {},
            "user_profile": {},
        },
    )
    client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "这是第二轮",
            "multimodal_features": {},
            "user_profile": {},
        },
    )
    state_snapshot = compiled_graph.get_state(
        {"configurable": {"thread_id": session_id}}
    )
    assert len(state_snapshot.values["chat_history"]) >= 4
