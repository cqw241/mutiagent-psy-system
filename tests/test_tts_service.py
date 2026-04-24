import asyncio
import base64
from types import SimpleNamespace

import httpx

from app.core.config import Settings
from app.services import tts_service


async def _collect_chunks(service: tts_service.BaseTTSService, text: str):
    return [chunk async for chunk in service.stream_audio(text)]


class _AsyncTextStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[str]):
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk.encode("utf-8")

    async def aclose(self):
        return None


def test_edge_tts_service_supports_legacy_communicate_signature(monkeypatch):
    seen_calls: list[dict] = []

    class LegacyCommunicate:
        def __init__(self, text, voice, rate, volume):
            seen_calls.append(
                {
                    "text": text,
                    "voice": voice,
                    "rate": rate,
                    "volume": volume,
                }
            )

        async def stream(self):
            yield {"type": "audio", "data": b"legacy-mp3"}

    monkeypatch.setattr(
        tts_service,
        "edge_tts",
        SimpleNamespace(Communicate=LegacyCommunicate),
    )

    service = tts_service.EdgeTTSService(Settings())

    chunks = asyncio.run(_collect_chunks(service, "你好"))

    assert seen_calls == [
        {
            "text": "你好",
            "voice": "zh-CN-XiaoxiaoNeural",
            "rate": "+0%",
            "volume": "+0%",
        }
    ]
    assert len(chunks) == 1
    assert chunks[0].audio_bytes == b"legacy-mp3"
    assert chunks[0].mime_type == "audio/mpeg"
    assert chunks[0].output_format == "audio-24khz-48kbitrate-mono-mp3"


def test_edge_tts_service_retries_transient_failure_without_emitting_partial_audio(
    monkeypatch,
):
    attempts: list[str] = []

    class FlakyCommunicate:
        def __init__(self, text, voice, rate, volume):
            attempts.append(text)
            self.attempt_number = len(attempts)

        async def stream(self):
            if self.attempt_number == 1:
                yield {"type": "audio", "data": b"partial-chunk"}
                raise ConnectionResetError("connection reset by peer")

            yield {"type": "audio", "data": b"full-chunk-1"}
            yield {"type": "audio", "data": b"full-chunk-2"}

    monkeypatch.setattr(
        tts_service,
        "edge_tts",
        SimpleNamespace(Communicate=FlakyCommunicate),
    )

    service = tts_service.EdgeTTSService(Settings())

    chunks = asyncio.run(_collect_chunks(service, "这是一整句要被完整读出来的话。"))

    assert attempts == ["这是一整句要被完整读出来的话。", "这是一整句要被完整读出来的话。"]
    assert [chunk.audio_bytes for chunk in chunks] == [b"full-chunk-1", b"full-chunk-2"]


def test_qwen_tts_service_downloads_audio_from_dashscope(monkeypatch):
    seen_requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append((request.method, str(request.url)))

        if request.method == "POST":
            assert str(request.url) == (
                "https://dashscope.aliyuncs.com/api/v1/"
                "services/aigc/multimodal-generation/generation"
            )
            assert request.headers["Authorization"] == "Bearer test-tts-key"
            payload = request.read().decode("utf-8")
            assert '"model":"qwen-tts-latest"' in payload
            assert '"text":"你好，今晚先慢慢放松一下。"' in payload
            assert '"voice":"Serena"' in payload
            assert '"language_type":"Chinese"' in payload
            return httpx.Response(
                200,
                json={
                    "output": {
                        "audio": {
                            "url": "https://dashscope-result.example.com/audio.wav"
                        }
                    }
                },
            )

        assert request.method == "GET"
        assert str(request.url) == "https://dashscope-result.example.com/audio.wav"
        return httpx.Response(
            200,
            headers={"Content-Type": "audio/wav"},
            content=b"fake-wav-audio",
        )

    service = tts_service.QwenTTSService(
        Settings(
            tts_provider="dashscope",
            tts_api_key="test-tts-key",
            tts_model="qwen-tts-latest",
            tts_voice="Serena",
        ),
        transport=httpx.MockTransport(handler),
    )

    chunks = asyncio.run(_collect_chunks(service, "你好，今晚先慢慢放松一下。"))

    assert seen_requests == [
        (
            "POST",
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        ),
        ("GET", "https://dashscope-result.example.com/audio.wav"),
    ]
    assert len(chunks) == 1
    assert chunks[0].audio_bytes == b"fake-wav-audio"
    assert chunks[0].mime_type == "audio/wav"
    assert chunks[0].output_format == "wav"


def test_qwen_tts_service_streams_pcm_chunks_from_dashscope_sse():
    seen_requests: list[tuple[str, str]] = []

    pcm_chunk_1 = base64.b64encode(b"\x01\x02\x03\x04").decode("ascii")
    pcm_chunk_2 = base64.b64encode(b"\x05\x06\x07\x08").decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append((request.method, str(request.url)))

        assert request.method == "POST"
        assert str(request.url) == (
            "https://dashscope.aliyuncs.com/api/v1/"
            "services/aigc/multimodal-generation/generation"
        )
        assert request.headers["Authorization"] == "Bearer test-tts-key"
        assert request.headers["X-DashScope-SSE"] == "enable"

        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=_AsyncTextStream(
                [
                    (
                        'data: {"output":{"audio":{"data":"'
                        f"{pcm_chunk_1}"
                        '"}}}\n\n'
                    ),
                    (
                        'data: {"output":{"audio":{"data":"'
                        f"{pcm_chunk_2}"
                        '"}}}\n\n'
                    ),
                    'data: {"output":{"audio":{"url":"https://dashscope-result.example.com/final.wav"}}}\n\n',
                ]
            ),
        )

    service = tts_service.QwenTTSService(
        Settings(
            tts_provider="dashscope",
            tts_api_key="test-tts-key",
            tts_model="qwen-tts-latest",
            tts_voice="Serena",
        ),
        transport=httpx.MockTransport(handler),
    )

    chunks = asyncio.run(_collect_chunks(service, "请慢慢说，我们一步一步来。"))

    assert seen_requests == [
        (
            "POST",
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        )
    ]
    assert [chunk.audio_bytes for chunk in chunks] == [b"\x01\x02\x03\x04", b"\x05\x06\x07\x08"]
    assert all(chunk.mime_type == "audio/pcm" for chunk in chunks)
    assert all(chunk.output_format == "pcm" for chunk in chunks)


def test_qwen_tts_service_retries_transient_failure_before_emitting_audio():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts

        if request.method == "POST":
            attempts += 1
            if attempts == 1:
                raise httpx.ConnectError("temporary network failure", request=request)
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                stream=_AsyncTextStream(
                    [
                        'data: {"output":{"audio":{"data":"cmVjb3ZlcmVkLXBjbQ=="}}}\n\n',
                    ]
                ),
            )

        raise AssertionError("streaming mode should not download audio urls in this test")

    service = tts_service.QwenTTSService(
        Settings(
            tts_provider="dashscope",
            tts_api_key="test-tts-key",
            tts_model="qwen-tts-latest",
            tts_voice="Serena",
        ),
        transport=httpx.MockTransport(handler),
    )

    chunks = asyncio.run(_collect_chunks(service, "这句话需要完整读出来。"))

    assert attempts == 2
    assert [chunk.audio_bytes for chunk in chunks] == [b"recovered-pcm"]


def test_qwen_tts_service_falls_back_to_edge_tts_after_forbidden_response(monkeypatch):
    seen_edge_calls: list[str] = []

    class FallbackCommunicate:
        def __init__(self, text, voice, rate, volume):
            seen_edge_calls.append(text)

        async def stream(self):
            yield {"type": "audio", "data": b"edge-fallback-mp3"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(403, request=request)

    monkeypatch.setattr(
        tts_service,
        "edge_tts",
        SimpleNamespace(Communicate=FallbackCommunicate),
    )

    service = tts_service.QwenTTSService(
        Settings(
            tts_provider="dashscope",
            tts_api_key="llm-key-without-tts-permission",
            tts_model="qwen-tts-latest",
            tts_voice="Serena",
        ),
        transport=httpx.MockTransport(handler),
    )

    chunks = asyncio.run(_collect_chunks(service, "语音回复需要兜底播放。"))

    assert seen_edge_calls == ["语音回复需要兜底播放。"]
    assert len(chunks) == 1
    assert chunks[0].audio_bytes == b"edge-fallback-mp3"
    assert chunks[0].mime_type == "audio/mpeg"


def test_get_tts_service_returns_qwen_provider_by_default():
    service = tts_service.get_tts_service(
        Settings(
            tts_provider="dashscope",
            tts_api_key="test-tts-key",
            tts_model="qwen-tts-latest",
        )
    )

    assert isinstance(service, tts_service.QwenTTSService)
