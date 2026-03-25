import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.api.routes import ws_chat
from app.core.config import get_settings


def test_ws_chat_emits_stage_token_final_and_end_events():
    client = TestClient(app)
    with client.websocket_connect("/ws/chat/session-ws-1") as websocket:
        websocket.send_json(
            {
                "message": "最近有点难受",
                "multimodal_features": {"facial_emotion": "sad"},
                "user_profile": {"school": "demo-university"},
            }
        )

        event_types = []
        final_payload = None
        for _ in range(200):
            data = websocket.receive_json()
            event_types.append(data["type"])
            if data["type"] == "final":
                final_payload = data
            if data["type"] == "end":
                break

        assert "stage" in event_types
        assert "token" in event_types
        assert "final" in event_types
        assert event_types[-1] == "end"
        assert final_payload is not None
        assert "risk_level" not in final_payload


class _FakeVoiceTranscriber:
    def __init__(self):
        self.chunks = []

    def process_audio_chunk(self, chunk):
        self.chunks.append(chunk)
        if chunk == b"voice-frame":
            return ["我最近有点难受"]
        return []

    def flush(self):
        return ""

    def process_audio_chunk_with_segments(self, chunk):
        self.chunks.append(chunk)
        if chunk != b"voice-frame":
            return []
        return [
            _FakeVoiceSegment(
                transcript="我最近有点难受",
                segment_id="segment-000001",
                start_ms=0,
                end_ms=420,
                duration_ms=420,
            )
        ]

    def flush_segment(self):
        return None


class _FakeVoiceSegment:
    def __init__(self, transcript, segment_id, start_ms, end_ms, duration_ms):
        self.transcript = transcript
        self.segment_id = segment_id
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.duration_ms = duration_ms
        self.acoustic_features = {
            "pause_count": 1,
            "pause_total_ms": 120,
            "pause_mean_ms": 120.0,
            "voiced_duration_ms": 300,
            "speech_ratio": 0.714,
            "mean_f0": None,
            "f0_std": None,
            "energy_mean": 0.1,
            "energy_std": 0.02,
            "rms_mean": 0.2,
            "rms_std": 0.03,
        }

    def to_state_dict(self):
        return {
            "segment_id": self.segment_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "transcript": self.transcript,
            "acoustic_features": self.acoustic_features,
        }


def test_voice_ws_emits_transcript_stage_token_final_and_end_events(monkeypatch):
    monkeypatch.setattr(
        ws_chat,
        "create_voice_transcriber",
        lambda: _FakeVoiceTranscriber(),
    )

    client = TestClient(app)
    with client.websocket_connect("/ws/voice-chat/session-voice-1") as websocket:
        websocket.send_bytes(b"voice-frame")
        websocket.send_json(
            {
                "type": "input_audio_buffer.commit",
                "multimodal_features": {"voice_energy": "elevated"},
                "user_profile": {"school": "demo-university"},
            }
        )

        event_types = []
        transcript_payload = None
        final_payload = None
        for _ in range(200):
            data = websocket.receive_json()
            event_types.append(data["type"])
            if data["type"] == "transcript":
                transcript_payload = data
            if data["type"] == "final":
                final_payload = data
            if data["type"] == "end":
                break

        assert transcript_payload["type"] == "transcript"
        assert transcript_payload["text"] == "我最近有点难受"
        assert transcript_payload["segment_id"] == "segment-000001"
        assert transcript_payload["duration_ms"] == 420
        assert transcript_payload["acoustic_features"]["pause_count"] == 1
        assert "stage" in event_types
        assert "token" in event_types
        assert "final" in event_types
        assert event_types[-1] == "end"
        assert final_payload is not None
        assert "trace" in final_payload
        assert final_payload["trace"]["latest_voice_segment"]["segment_id"] == "segment-000001"
        assert "risk_calibration" in final_payload["trace"]


def test_voice_ws_trace_exposes_emotion2vec_status(monkeypatch):
    monkeypatch.setattr(
        ws_chat,
        "create_voice_transcriber",
        lambda: _FakeVoiceTranscriber(),
    )
    monkeypatch.setenv("ENABLE_EMOTION2VEC", "true")
    monkeypatch.delenv("EMOTION2VEC_MODEL_DIR", raising=False)
    get_settings.cache_clear()

    client = TestClient(app)
    try:
        with client.websocket_connect("/ws/voice-chat/session-voice-e2v") as websocket:
            websocket.send_bytes(b"voice-frame")
            websocket.send_json(
                {
                    "type": "input_audio_buffer.commit",
                    "multimodal_features": {"voice_energy": "elevated"},
                    "user_profile": {"school": "demo-university"},
                }
            )

            final_payload = None
            for _ in range(200):
                data = websocket.receive_json()
                if data["type"] == "final":
                    final_payload = data
                if data["type"] == "end":
                    break

            assert final_payload is not None
            assert final_payload["trace"]["emotion2vec"]["enabled"] is True
            assert final_payload["trace"]["emotion2vec"]["status"] == "unavailable"
            assert final_payload["trace"]["emotion2vec"]["used"] is False
    finally:
        get_settings.cache_clear()


class _DisconnectRuntimeVoiceWebSocket:
    def __init__(self):
        self.accepted = False
        self.sent_payloads = []

    async def accept(self):
        self.accepted = True

    async def receive(self):
        raise RuntimeError(
            'Cannot call "receive" once a disconnect message has been received.'
        )

    async def send_json(self, payload):
        self.sent_payloads.append(payload)


def test_voice_ws_disconnect_runtime_error_exits_cleanly(monkeypatch):
    monkeypatch.setattr(
        ws_chat,
        "create_voice_transcriber",
        lambda: _FakeVoiceTranscriber(),
    )

    websocket = _DisconnectRuntimeVoiceWebSocket()

    asyncio.run(ws_chat.websocket_voice_chat(websocket, "session-voice-disconnect"))

    assert websocket.accepted is True
    assert websocket.sent_payloads == []
