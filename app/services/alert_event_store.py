"""File-backed high-risk alert event store."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models.schemas import (
    AlertAckStatus,
    AlertDeliveryStatus,
    AlertEvent,
    AlertHandlerStatus,
    RiskLevel,
)


def mask_session_id(session_id: str) -> str:
    """Return the stable masked session id used in alert payloads."""

    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return f"session-{digest[:10]}"


class FileAlertEventStore:
    """Small JSONL-backed store for high-risk alert events."""

    def __init__(self, path: str | Path = ".alert-events/alert-events.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        session_id: str,
        trace_id: str,
        risk_level: RiskLevel,
        latest_risk_evidence: dict[str, Any],
        summary: str,
    ) -> AlertEvent:
        now = _utc_now()
        event = AlertEvent(
            alert_event_id=f"alert_{uuid4().hex}",
            trigger_time=now,
            updated_at=now,
            masked_session_id=mask_session_id(session_id),
            risk_level=risk_level,
            latest_risk_evidence=latest_risk_evidence,
            trace_id=trace_id,
            summary=summary,
        )
        events = self._read_events()
        events[event.alert_event_id] = event
        self._write_events(events)
        return event

    def update(
        self,
        alert_event_id: str,
        *,
        delivery_status: AlertDeliveryStatus | None = None,
        ack_status: AlertAckStatus | None = None,
        handler_status: AlertHandlerStatus | None = None,
    ) -> AlertEvent:
        events = self._read_events()
        event = events[alert_event_id]
        updates: dict[str, Any] = {"updated_at": _utc_now()}
        if delivery_status is not None:
            updates["delivery_status"] = delivery_status
        if ack_status is not None:
            updates["ack_status"] = ack_status
        if handler_status is not None:
            updates["handler_status"] = handler_status
            if handler_status != "created":
                updates["ack_status"] = "acknowledged"
        updated = event.model_copy(update=updates)
        events[alert_event_id] = updated
        self._write_events(events)
        return updated

    def get(self, alert_event_id: str) -> AlertEvent | None:
        return self._read_events().get(alert_event_id)

    def list(self) -> list[AlertEvent]:
        return sorted(self._read_events().values(), key=lambda event: event.trigger_time)

    def _read_events(self) -> dict[str, AlertEvent]:
        if not self.path.exists():
            return {}
        events: dict[str, AlertEvent] = {}
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                event = AlertEvent.model_validate_json(line)
                events[event.alert_event_id] = event
        return events

    def _write_events(self, events: dict[str, AlertEvent]) -> None:
        ordered = sorted(events.values(), key=lambda event: event.trigger_time)
        with self.path.open("w", encoding="utf-8") as handle:
            for event in ordered:
                handle.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
