import asyncio
import base64

from fastapi.testclient import TestClient

from app.main import app
from app.api.routes import ws_chat
from app.core.config import get_settings
from app.services.tts_service import TTSChunk


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


class _FakeTTSService:
    def __init__(self):
        self.calls = []

    async def stream_audio(self, text):
        self.calls.append(text)
        yield TTSChunk(
            audio_bytes=b"fake-mp3-chunk-1",
            mime_type="audio/mpeg",
            output_format="audio-24khz-48kbitrate-mono-mp3",
        )
        yield TTSChunk(
            audio_bytes=b"fake-mp3-chunk-2",
            mime_type="audio/mpeg",
            output_format="audio-24khz-48kbitrate-mono-mp3",
        )


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


def test_voice_ws_emits_tts_audio_events_when_response_audio_requested(monkeypatch):
    monkeypatch.setattr(
        ws_chat,
        "create_voice_transcriber",
        lambda: _FakeVoiceTranscriber(),
    )

    fake_tts = _FakeTTSService()
    monkeypatch.setattr(
        "app.nodes.response_generator.get_tts_service",
        lambda *_args, **_kwargs: fake_tts,
        raising=False,
    )

    client = TestClient(app)
    with client.websocket_connect("/ws/voice-chat/session-voice-tts-1") as websocket:
        websocket.send_json(
            {
                "multimodal_features": {
                    "voice_energy": "elevated",
                    "response_audio": True,
                    "call_mode": "video",
                },
                "user_profile": {"school": "demo-university"},
            }
        )
        websocket.send_bytes(b"voice-frame")
        websocket.send_json(
            {
                "type": "input_audio_buffer.commit",
                "multimodal_features": {
                    "voice_energy": "elevated",
                    "response_audio": True,
                    "call_mode": "video",
                },
                "user_profile": {"school": "demo-university"},
            }
        )

        tts_audio_events = []
        tts_end_events = []
        for _ in range(300):
            data = websocket.receive_json()
            if data["type"] == "tts_audio":
                tts_audio_events.append(data)
            if data["type"] == "tts_end":
                tts_end_events.append(data)
            if data["type"] == "end":
                break

        assert fake_tts.calls
        assert len(tts_audio_events) == 2 * len(fake_tts.calls)
        assert len(tts_end_events) == len(fake_tts.calls)
        assert base64.b64decode(tts_audio_events[0]["payload"]) == b"fake-mp3-chunk-1"
        assert tts_audio_events[0]["mime_type"] == "audio/mpeg"


def test_voice_ws_trace_exposes_emotion2vec_status(monkeypatch):
    monkeypatch.setattr(
        ws_chat,
        "create_voice_transcriber",
        lambda: _FakeVoiceTranscriber(),
    )
    monkeypatch.setenv("ENABLE_EMOTION2VEC", "true")
    monkeypatch.setenv("EMOTION2VEC_MODEL_DIR", "/tmp/emotion2vec")

    async def _fake_analyze(segment):
        assert segment.segment_id == "segment-000001"
        return {
            "status": "ok",
            "source": "emotion2vec_plus_large",
            "model_dir": "/tmp/emotion2vec",
            "emotion_label": "sad",
            "confidence": 0.88,
            "topk": [{"label": "sad", "score": 0.88}],
            "observation": "语音情绪类别更接近 sad。",
            "raw_output": {"labels": ["sad"], "scores": [0.88]},
            "error": None,
        }

    monkeypatch.setattr(
        ws_chat,
        "_analyze_emotion2vec_for_segment",
        _fake_analyze,
        raising=False,
    )
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
            assert final_payload["trace"]["emotion2vec"]["status"] == "ok"
            assert final_payload["trace"]["emotion2vec"]["used"] is True
            assert final_payload["trace"]["emotion2vec"]["label"] == "sad"
            assert "audio_pcm" not in final_payload["trace"]["latest_voice_segment"]
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


def test_dispatch_voice_segment_skips_blank_transcript(monkeypatch):
    sent_payloads = []
    stream_calls = []

    async def _fake_send(_websocket, payload):
        sent_payloads.append(payload)
        return True

    async def _fake_stream_graph_reply(**kwargs):
        stream_calls.append(kwargs)

    monkeypatch.setattr(ws_chat, "_send_json_if_open", _fake_send)
    monkeypatch.setattr(ws_chat, "_stream_graph_reply", _fake_stream_graph_reply)

    segment = _FakeVoiceSegment(
        transcript="   ",
        segment_id="segment-blank",
        start_ms=0,
        end_ms=120,
        duration_ms=120,
    )

    processed = asyncio.run(
        ws_chat._dispatch_voice_segment(
            websocket=object(),
            session_id="session-voice-blank",
            segment=segment,
            voice_context={
                "user_profile": {},
                "multimodal_features": {},
                "face_segments": [],
            },
            emotion2vec_reading=None,
        )
    )

    assert processed is False
    assert sent_payloads == []
    assert stream_calls == []


def test_dispatch_voice_segment_normalizes_transcript_before_sending(monkeypatch):
    sent_payloads = []
    stream_calls = []
    voice_context = {
        "user_profile": {"school": "demo-university"},
        "multimodal_features": {"response_audio": True},
        "face_segments": [{"frame_id": "face-1"}],
    }

    async def _fake_send(_websocket, payload):
        sent_payloads.append(payload)
        return True

    async def _fake_stream_graph_reply(**kwargs):
        stream_calls.append(kwargs)

    monkeypatch.setattr(ws_chat, "_send_json_if_open", _fake_send)
    monkeypatch.setattr(ws_chat, "_stream_graph_reply", _fake_stream_graph_reply)

    segment = _FakeVoiceSegment(
        transcript="  我最近有点难受  ",
        segment_id="segment-normalized",
        start_ms=0,
        end_ms=420,
        duration_ms=420,
    )

    processed = asyncio.run(
        ws_chat._dispatch_voice_segment(
            websocket=object(),
            session_id="session-voice-normalized",
            segment=segment,
            voice_context=voice_context,
            emotion2vec_reading={"status": "disabled"},
        )
    )

    assert processed is True
    assert sent_payloads[0]["type"] == "transcript"
    assert sent_payloads[0]["text"] == "我最近有点难受"
    assert stream_calls[0]["message"] == "我最近有点难受"
    assert stream_calls[0]["face_segments"] == [{"frame_id": "face-1"}]
    assert stream_calls[0]["user_profile"] == {"school": "demo-university"}
    assert voice_context["face_segments"] == []
