"""TTS 服务适配层。

职责：
1. 封装 qwen-tts-latest / edge-tts 的异步接口
2. 统一向上游暴露 JSON 友好的音频块元信息
3. 在依赖缺失或运行失败时安全降级，不中断主链路
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx
from app.core.config import Settings

try:
    import edge_tts
except ImportError:  # pragma: no cover - 测试环境不强依赖真实 SDK
    edge_tts = None

logger = logging.getLogger(__name__)
_LEGACY_EDGE_TTS_OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
_TTS_MAX_ATTEMPTS = 2
_QWEN_TTS_GENERATION_PATH = "/services/aigc/multimodal-generation/generation"
_QWEN_TTS_DEFAULT_MIME_TYPE = "audio/wav"
_QWEN_TTS_DEFAULT_OUTPUT_FORMAT = "wav"
_QWEN_TTS_STREAM_MIME_TYPE = "audio/pcm"
_QWEN_TTS_STREAM_OUTPUT_FORMAT = "pcm"
_QWEN_TTS_FALLBACK_VOICE = "Serena"


@dataclass(frozen=True)
class TTSChunk:
    audio_bytes: bytes
    mime_type: str
    output_format: str


class BaseTTSService(ABC):
    @abstractmethod
    async def stream_audio(self, text: str) -> AsyncIterator[TTSChunk]:
        """将文本转为音频块并流式返回。"""


def _infer_mime_type(output_format: str) -> str:
    normalized = output_format.lower()
    if "mp3" in normalized:
        return "audio/mpeg"
    if "opus" in normalized or "webm" in normalized:
        return "audio/webm"
    if "pcm" in normalized or "wav" in normalized:
        return "audio/wav"
    return "application/octet-stream"


def _infer_output_format_from_mime_type(mime_type: str | None) -> str:
    if not mime_type:
        return _QWEN_TTS_DEFAULT_OUTPUT_FORMAT

    normalized = mime_type.split(";", 1)[0].strip().lower()
    if normalized == "audio/mpeg":
        return "mp3"
    if normalized in {"audio/wav", "audio/x-wav"}:
        return "wav"
    if normalized == "audio/webm":
        return "webm"
    return _QWEN_TTS_DEFAULT_OUTPUT_FORMAT


def _communicate_supports_output_format(tts_module: object | None) -> bool:
    if tts_module is None:
        return False

    communicate_cls = getattr(tts_module, "Communicate", None)
    if communicate_cls is None:
        return False

    try:
        parameters = inspect.signature(communicate_cls.__init__).parameters
    except (TypeError, ValueError):
        return False

    return "output_format" in parameters


def _should_retry_tts_exception(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError, OSError, httpx.TransportError)):
        return True

    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}

    if isinstance(exc, httpx.InvalidURL):
        return True

    message = str(exc).lower()
    retry_markers = (
        "cannot connect to host",
        "connection reset",
        "server disconnected",
        "timed out",
        "temporarily unavailable",
    )
    return any(marker in message for marker in retry_markers)


def _extract_qwen_audio_url(payload: dict[str, Any]) -> str:
    output = payload.get("output")
    if not isinstance(output, dict):
        return ""

    audio = output.get("audio")
    if not isinstance(audio, dict):
        return ""

    url = audio.get("url")
    if not isinstance(url, str):
        return ""

    return url.strip()


def _extract_qwen_audio_data(payload: dict[str, Any]) -> str:
    output = payload.get("output")
    if not isinstance(output, dict):
        return ""

    audio = output.get("audio")
    if not isinstance(audio, dict):
        return ""

    data = audio.get("data")
    if not isinstance(data, str):
        return ""

    return data.strip()


async def _iter_sse_data_events(response: httpx.Response) -> AsyncIterator[str]:
    data_lines: list[str] = []

    async for line in response.aiter_lines():
        if not line:
            if data_lines:
                yield "\n".join(data_lines)
                data_lines = []
            continue

        if line.startswith(":"):
            continue

        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if data_lines:
        yield "\n".join(data_lines)


def _normalize_qwen_voice(voice: str) -> str:
    candidate = voice.strip()
    if not candidate:
        return _QWEN_TTS_FALLBACK_VOICE

    if "Neural" in candidate or candidate.startswith(("zh-", "en-", "ja-")):
        logger.warning(
            "Configured qwen TTS voice %s looks like a legacy edge-tts voice; "
            "falling back to %s.",
            candidate,
            _QWEN_TTS_FALLBACK_VOICE,
        )
        return _QWEN_TTS_FALLBACK_VOICE

    return candidate


class EdgeTTSService(BaseTTSService):
    """基于 edge-tts 的流式中文 TTS。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._supports_output_format = _communicate_supports_output_format(edge_tts)
        self.output_format = (
            settings.tts_output_format
            if self._supports_output_format
            else _LEGACY_EDGE_TTS_OUTPUT_FORMAT
        )
        self.mime_type = _infer_mime_type(self.output_format)

        if (
            edge_tts is not None
            and not self._supports_output_format
            and settings.tts_output_format != self.output_format
        ):
            logger.warning(
                "Installed edge-tts does not support custom output_format; "
                "falling back to %s.",
                self.output_format,
            )

    async def stream_audio(self, text: str) -> AsyncIterator[TTSChunk]:
        if not self.settings.tts_enabled:
            return

        normalized_text = text.strip()
        if not normalized_text:
            return

        if edge_tts is None:
            logger.warning("edge-tts 未安装，跳过 TTS 合成。")
            return

        for attempt in range(1, _TTS_MAX_ATTEMPTS + 1):
            try:
                communicate_kwargs = {
                    "voice": self.settings.tts_voice,
                    "rate": self.settings.tts_rate,
                    "volume": self.settings.tts_volume,
                }
                if self._supports_output_format:
                    communicate_kwargs["output_format"] = self.settings.tts_output_format

                communicate = edge_tts.Communicate(normalized_text, **communicate_kwargs)
                buffered_chunks: list[TTSChunk] = []
                async for chunk in communicate.stream():
                    if chunk.get("type") != "audio":
                        continue
                    audio_bytes = chunk.get("data")
                    if not audio_bytes:
                        continue
                    buffered_chunks.append(
                        TTSChunk(
                            audio_bytes=audio_bytes,
                            mime_type=self.mime_type,
                            output_format=self.output_format,
                        )
                    )

                for buffered_chunk in buffered_chunks:
                    yield buffered_chunk
                return
            except Exception as exc:  # pragma: no cover - 真实依赖异常防御
                if attempt < _TTS_MAX_ATTEMPTS and _should_retry_tts_exception(exc):
                    logger.warning(
                        "edge-tts synthesis attempt %s/%s failed: %s; retrying.",
                        attempt,
                        _TTS_MAX_ATTEMPTS,
                        exc,
                    )
                    await asyncio.sleep(0.35 * attempt)
                    continue

                logger.warning("edge-tts synthesis failed: %s", exc)
                return


class QwenTTSService(BaseTTSService):
    """基于阿里云百炼 qwen-tts-latest 的句级 TTS。"""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.base_url = settings.tts_base_url.rstrip("/")
        self.api_key = settings.tts_api_key
        self.model = settings.tts_model
        self.voice = _normalize_qwen_voice(settings.tts_qwen_voice)
        self.language_type = settings.tts_qwen_language_type
        self.timeout_seconds = settings.tts_timeout_seconds
        self.mime_type = _QWEN_TTS_DEFAULT_MIME_TYPE
        self.output_format = _QWEN_TTS_DEFAULT_OUTPUT_FORMAT

    async def stream_audio(self, text: str) -> AsyncIterator[TTSChunk]:
        if not self.settings.tts_enabled:
            return

        normalized_text = text.strip()
        if not normalized_text:
            return

        if not self.api_key:
            logger.warning("DashScope TTS API key is missing; skipping qwen TTS synthesis.")
            return

        if os.getenv("PYTEST_CURRENT_TEST") and self.transport is None:
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": {
                "text": normalized_text,
                "voice": self.voice,
                "language_type": self.language_type,
            },
        }

        for attempt in range(1, _TTS_MAX_ATTEMPTS + 1):
            emitted_audio = False
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds,
                    transport=self.transport,
                    follow_redirects=True,
                ) as client:
                    request_headers = {
                        **headers,
                        "X-DashScope-SSE": "enable",
                    }
                    audio_url = ""

                    async with client.stream(
                        "POST",
                        f"{self.base_url}{_QWEN_TTS_GENERATION_PATH}",
                        headers=request_headers,
                        json=payload,
                    ) as response:
                        response.raise_for_status()
                        content_type = response.headers.get("Content-Type", "").lower()

                        if "text/event-stream" in content_type:
                            latest_payload: dict[str, Any] | None = None
                            async for event_data in _iter_sse_data_events(response):
                                if not event_data or event_data == "[DONE]":
                                    continue

                                event_payload = json.loads(event_data)
                                latest_payload = event_payload
                                audio_data = _extract_qwen_audio_data(event_payload)
                                if not audio_data:
                                    continue

                                audio_bytes = base64.b64decode(audio_data)
                                if not audio_bytes:
                                    continue

                                emitted_audio = True
                                yield TTSChunk(
                                    audio_bytes=audio_bytes,
                                    mime_type=_QWEN_TTS_STREAM_MIME_TYPE,
                                    output_format=_QWEN_TTS_STREAM_OUTPUT_FORMAT,
                                )

                            if emitted_audio:
                                return

                            if latest_payload is not None:
                                audio_url = _extract_qwen_audio_url(latest_payload)
                        else:
                            raw_body = await response.aread()
                            fallback_payload = json.loads(raw_body.decode("utf-8"))
                            audio_url = _extract_qwen_audio_url(fallback_payload)

                    if not audio_url:
                        raise ValueError(
                            "DashScope TTS response did not contain streamed audio data or audio url."
                        )

                    audio_response = await client.get(audio_url)
                    audio_response.raise_for_status()

                    audio_bytes = audio_response.content
                    if not audio_bytes:
                        raise ValueError("DashScope TTS audio download returned empty content.")

                    content_type = audio_response.headers.get("Content-Type")
                    mime_type = (
                        content_type.split(";", 1)[0].strip() if content_type else self.mime_type
                    )
                    output_format = _infer_output_format_from_mime_type(mime_type)
                    yield TTSChunk(
                        audio_bytes=audio_bytes,
                        mime_type=mime_type or self.mime_type,
                        output_format=output_format,
                    )
                    return
            except Exception as exc:  # pragma: no cover - 真实依赖异常防御
                if (
                    attempt < _TTS_MAX_ATTEMPTS
                    and not emitted_audio
                    and _should_retry_tts_exception(exc)
                ):
                    logger.warning(
                        "qwen-tts synthesis attempt %s/%s failed: %s; retrying.",
                        attempt,
                        _TTS_MAX_ATTEMPTS,
                        exc,
                    )
                    await asyncio.sleep(0.35 * attempt)
                    continue

                logger.warning("qwen-tts synthesis failed: %s", exc)
                return


def get_tts_service(settings: Settings) -> BaseTTSService:
    """返回默认 TTS 服务实现。"""

    if settings.tts_provider == "edge_tts":
        return EdgeTTSService(settings)
    return QwenTTSService(settings)
