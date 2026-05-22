from pathlib import Path

from app.services.alert_event_store import FileAlertEventStore


def test_file_alert_event_store_persists_created_event(tmp_path: Path):
    store_path = tmp_path / "alert-events.jsonl"
    store = FileAlertEventStore(store_path)

    event = store.create(
        session_id="session-123",
        trace_id="trace-1",
        risk_level="high",
        latest_risk_evidence={"keywords": ["不想活了"]},
        summary="检测到需要人工关注的高风险心理支持对话，请尽快复核。",
    )

    assert event.alert_event_id.startswith("alert_")
    assert event.masked_session_id != "session-123"
    assert event.risk_level == "high"
    assert event.delivery_status == "created"
    assert event.handler_status == "created"
    assert event.latest_risk_evidence == {"keywords": ["不想活了"]}

    reloaded = FileAlertEventStore(store_path)
    assert reloaded.get(event.alert_event_id) == event
    assert reloaded.list()[0] == event


def test_file_alert_event_store_updates_delivery_and_handler_statuses(tmp_path: Path):
    store = FileAlertEventStore(tmp_path / "alert-events.jsonl")
    event = store.create(
        session_id="session-123",
        trace_id="trace-1",
        risk_level="high",
        latest_risk_evidence={"keywords": ["不想活了"]},
        summary="检测到需要人工关注的高风险心理支持对话，请尽快复核。",
    )

    delivered = store.update(
        event.alert_event_id,
        delivery_status="delivered",
        handler_status="acknowledged",
    )
    closed = store.update(event.alert_event_id, handler_status="closed")

    assert delivered.delivery_status == "delivered"
    assert delivered.handler_status == "acknowledged"
    assert delivered.ack_status == "acknowledged"
    assert closed.delivery_status == "delivered"
    assert closed.handler_status == "closed"
    assert closed.ack_status == "acknowledged"
    assert store.get(event.alert_event_id) == closed


def test_file_alert_event_store_records_delivery_failure(tmp_path: Path):
    store = FileAlertEventStore(tmp_path / "alert-events.jsonl")
    event = store.create(
        session_id="session-123",
        trace_id="trace-1",
        risk_level="high",
        latest_risk_evidence={"keywords": ["不想活了"]},
        summary="检测到需要人工关注的高风险心理支持对话，请尽快复核。",
    )

    failed = store.update(event.alert_event_id, delivery_status="delivery_failed")

    assert failed.delivery_status == "delivery_failed"
    assert failed.handler_status == "created"
    assert failed.ack_status == "unacknowledged"
