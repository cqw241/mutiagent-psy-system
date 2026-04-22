"""回复生成节点。

职责：
1. 依据风险等级生成温和、有同理心的回复
2. 高风险场景下，在 referral_agent 的过渡话术基础上做最终包装
3. 低/中风险场景下，用 LLM 流式生成自然对话

设计变更（本次重构）：
- 转介相关逻辑（hotline_card、webhook 告警）已解耦到 referral_agent
- 本节点只负责回复生成，不再处理告警闭环
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

from app.core.config import get_settings
from app.models.schemas import ChatMessage
from app.prompts import (
    build_response_generator_system_prompt,
    build_response_generator_user_prompt,
)
from app.services.llm_client import BaseLLMClient, LiteLLMClient
from app.services.tts_service import BaseTTSService, get_tts_service
from app.utils.state_helpers import latest_user_message, merge_agent_judgment
from langgraph.config import get_stream_writer

_TTS_SENTENCE_ENDINGS = {"。", "！", "？", "!", "?"}
_TTS_TRAILING_CLOSERS = {'"', "'", "”", "’", "）", "】", "」", "』"}


def _safe_stream_writer():
    try:
        return get_stream_writer()
    except RuntimeError:
        return lambda _payload: None


def _split_complete_tts_sentences(buffer: str) -> tuple[list[str], str]:
    sentences: list[str] = []
    start = 0
    index = 0

    while index < len(buffer):
        if buffer[index] not in _TTS_SENTENCE_ENDINGS:
            index += 1
            continue

        end = index + 1
        while end < len(buffer) and buffer[end] in _TTS_TRAILING_CLOSERS:
            end += 1

        sentence = buffer[start:end].strip()
        if sentence:
            sentences.append(sentence)
        start = end
        index = end

    return sentences, buffer[start:]


class _StreamingTTSEmitter:
    def __init__(self, writer, tts_service: BaseTTSService) -> None:
        self._writer = writer
        self._tts_service = tts_service
        self._buffer = ""
        self._segment_index = 0
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._worker = asyncio.create_task(self._run())

    def ingest(self, chunk: str) -> None:
        self._buffer += chunk
        sentences, remainder = _split_complete_tts_sentences(self._buffer)
        self._buffer = remainder
        for sentence in sentences:
            self._queue.put_nowait(sentence)

    async def finalize(self) -> None:
        trailing = self._buffer.strip()
        self._buffer = ""
        if trailing:
            await self._queue.put(trailing)
        await self._queue.put(None)
        await self._worker

    async def _run(self) -> None:
        while True:
            sentence = await self._queue.get()
            if sentence is None:
                return

            self._segment_index += 1
            segment_id = f"tts-{self._segment_index:04d}"

            try:
                emitted_audio = False
                async for chunk in self._tts_service.stream_audio(sentence):
                    emitted_audio = True
                    self._writer(
                        {
                            "type": "tts_audio",
                            "segment_id": segment_id,
                            "sequence": self._segment_index,
                            "mime_type": chunk.mime_type,
                            "output_format": chunk.output_format,
                            "payload": base64.b64encode(chunk.audio_bytes).decode("ascii"),
                        }
                    )
                if emitted_audio:
                    self._writer(
                        {
                            "type": "tts_end",
                            "segment_id": segment_id,
                            "sequence": self._segment_index,
                            "text": sentence,
                        }
                    )
            except Exception:
                # TTS 只做能力增强，不允许阻断主回复链路
                continue


async def _emit_token_chunk(
    writer,
    chunk: str,
    tts_emitter: _StreamingTTSEmitter | None,
) -> None:
    writer({"type": "token", "chunk": chunk})
    if tts_emitter is not None:
        tts_emitter.ingest(chunk)


async def _stream_text_to_writer(
    llm: BaseLLMClient,
    writer,
    system_prompt: str,
    user_prompt: str,
    fallback_text: str,
    tts_emitter: _StreamingTTSEmitter | None = None,
) -> str:
    parts: list[str] = []
    async for chunk in llm.stream_text(system_prompt, user_prompt, fallback_text):
        parts.append(chunk)
        await _emit_token_chunk(writer, chunk, tts_emitter)
    if tts_emitter is not None:
        await tts_emitter.finalize()
    return "".join(parts)


async def response_generator_node(
    state: dict[str, Any],
    llm_client: BaseLLMClient | None = None,
    tts_service: BaseTTSService | None = None,
) -> dict[str, Any]:
    """生成最终回复。"""

    settings = get_settings()
    llm = llm_client or LiteLLMClient(settings)
    writer = _safe_stream_writer()
    multimodal_features = state.get("multimodal_features", {})
    want_tts = bool(multimodal_features.get("response_audio")) and settings.tts_enabled
    tts_emitter = None
    if want_tts:
        tts_emitter = _StreamingTTSEmitter(
            writer,
            tts_service or get_tts_service(settings),
        )

    risk_level = state.get("risk_level", "low")
    latest_text = latest_user_message(state)
    used_llm = False

    stream_system_prompt = build_response_generator_system_prompt(
        state.get("peer_support_context", "")
    )

    if risk_level == "high":
        # 高风险：referral_agent 已设置了温和过渡话术作为 reply
        # 这里直接流式输出该 reply（不再调用 LLM 生成）
        existing_reply = state.get("reply", "")
        if existing_reply:
            for char in existing_reply:
                await _emit_token_chunk(writer, char, tts_emitter)
            reply = existing_reply
        else:
            # 兜底：referral_agent 未设置 reply 时，使用安全模板
            fallback = (
                "我注意到你现在可能正处在非常痛苦和危险的状态。请先不要独自承受，"
                "尽快联系你身边可信任的人、学校辅导员，或拨打心理援助热线寻求即时支持。"
            )
            for char in fallback:
                await _emit_token_chunk(writer, char, tts_emitter)
            reply = fallback
        if tts_emitter is not None:
            await tts_emitter.finalize()
    elif risk_level == "medium":
        used_llm = True
        user_prompt = build_response_generator_user_prompt(risk_level, latest_text)
        reply = await _stream_text_to_writer(
            llm,
            writer,
            stream_system_prompt,
            user_prompt,
            "听起来你最近承受了不少压力。你愿意和我继续说说，最近最让你难受的事情是什么吗？",
            tts_emitter=tts_emitter,
        )
    else:
        used_llm = True
        user_prompt = build_response_generator_user_prompt(risk_level, latest_text)
        reply = await _stream_text_to_writer(
            llm,
            writer,
            stream_system_prompt,
            user_prompt,
            "谢谢你愿意分享现在的感受。我会先陪你梳理一下，你最近最明显的情绪变化是什么？",
            tts_emitter=tts_emitter,
        )

    judgment = {
        "used_llm": used_llm,
        "risk_level": risk_level,
        "used_tts": want_tts,
        "has_peer_support_context": bool(state.get("peer_support_context")),
    }

    return {
        "reply": reply,
        "agent_judgments": merge_agent_judgment(
            state, "response_generator", judgment
        ),
        "chat_history": [ChatMessage(role="assistant", content=reply).model_dump()],
    }
