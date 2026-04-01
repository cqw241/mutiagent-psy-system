"""TTS 服务适配层。

职责：
1. 封装 edge-tts 的异步流式接口
2. 统一向上游暴露 JSON 友好的音频块元信息
3. 在依赖缺失或运行失败时安全降级，不中断主链路
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

from app.core.config import Settings

try:
    import edge_tts
except ImportError:  # pragma: no cover - 测试环境不强依赖真实 SDK
    edge_tts = None

logger = logging.getLogger(__name__)


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
    if "pcm" in normalized:
        return "audio/wav"
    return "application/octet-stream"


class EdgeTTSService(BaseTTSService):
    """基于 edge-tts 的流式中文 TTS。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mime_type = _infer_mime_type(settings.tts_output_format)

    async def stream_audio(self, text: str) -> AsyncIterator[TTSChunk]:
        if not self.settings.tts_enabled:
            return

        normalized_text = text.strip()
        if not normalized_text:
            return

        if edge_tts is None:
            logger.warning("edge-tts 未安装，跳过 TTS 合成。")
            return

        try:
            communicate = edge_tts.Communicate(
                normalized_text,
                voice=self.settings.tts_voice,
                rate=self.settings.tts_rate,
                volume=self.settings.tts_volume,
                output_format=self.settings.tts_output_format,
            )
            async for chunk in communicate.stream():
                if chunk.get("type") != "audio":
                    continue
                audio_bytes = chunk.get("data")
                if not audio_bytes:
                    continue
                yield TTSChunk(
                    audio_bytes=audio_bytes,
                    mime_type=self.mime_type,
                    output_format=self.settings.tts_output_format,
                )
        except Exception as exc:  # pragma: no cover - 真实依赖异常防御
            logger.warning("edge-tts synthesis failed: %s", exc)
            return


def get_tts_service(settings: Settings) -> BaseTTSService:
    """返回默认 TTS 服务实现。"""

    return EdgeTTSService(settings)
