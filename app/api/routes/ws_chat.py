"""WebSocket 聊天接口。

协议设计：
- {"type":"stage","name":"received","message":"..."}
- {"type":"stage","name":"rag_retriever_done","message":"..."}
- {"type":"token","chunk":"我"}
- {"type":"final","reply":"...", "referral_required": false, "hotline_card": null, "trace_id": "..."}
- {"type":"end"}
- {"type":"error","message":"..."}
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.graph.workflow import get_compiled_graph
from app.services.asr_service import (
    PCMChunkAudioTranscriber,
    FasterWhisperASRService,
    VoiceSegmentResult,
)
from app.services.trace_service import build_trace_payload
from app.utils.state_helpers import build_initial_state

router = APIRouter(tags=["ws-chat"])
compiled_graph = get_compiled_graph()
logger = logging.getLogger(__name__)

SAFE_STAGE_MAP = {
    "text_analyzer": ("text_analyzer_done", "正在认真理解你的感受。"),
    "voice_analyzer": ("voice_analyzer_done", "正在倾听你的语音信息。"),
    "face_analyzer": ("face_analyzer_done", "正在关注你的表情变化。"),
    "signal_aggregator": ("signal_aggregator_done", "正在整合多维度的信息。"),
    "rag_retriever": ("rag_retriever_done", "正在结合专业案例认真分析。"),
    "risk_assessor": ("risk_assessor_done", "正在谨慎评估当前支持策略。"),
    "referral_agent": ("referral_agent_done", "正在为你准备专业支持资源。"),
    "response_generator": ("response_generator_done", "正在组织一段温和、清晰的回应。"),
    # 保留旧名称兼容（过渡期）
    "information_extractor": ("information_extractor_done", "正在认真理解你的感受。"),
}


def _is_disconnect_runtime_error(exc: RuntimeError) -> bool:
    message = str(exc).lower()
    return (
        "disconnect message has been received" in message
        or "after sending 'websocket.close'" in message
        or "response already completed" in message
    )


def _websocket_is_closed(websocket: WebSocket) -> bool:
    return (
        websocket.client_state == WebSocketState.DISCONNECTED
        or websocket.application_state == WebSocketState.DISCONNECTED
    )


async def _send_json_if_open(websocket: WebSocket, payload: dict) -> bool:
    if _websocket_is_closed(websocket):
        return False

    try:
        await websocket.send_json(payload)
        return True
    except WebSocketDisconnect:
        return False
    except RuntimeError as exc:
        if _is_disconnect_runtime_error(exc):
            return False
        raise


def _try_create_voice_transcriber() -> PCMChunkAudioTranscriber | None:
    """尝试创建语音转写器，模型不可用时返回 None 并记录日志。"""
    try:
        asr_service = FasterWhisperASRService()
        return PCMChunkAudioTranscriber(asr_service=asr_service)
    except (FileNotFoundError, RuntimeError) as exc:
        logger.warning("ASR 模型加载失败，语音功能将降级为不可用: %s", exc)
        return None


def create_voice_transcriber() -> PCMChunkAudioTranscriber | None:
    """兼容测试和调用方的公共入口。"""
    return _try_create_voice_transcriber()


async def _stream_graph_reply(
    websocket: WebSocket,
    session_id: str,
    message: str,
    user_profile: dict | None = None,
    multimodal_features: dict | None = None,
    voice_segments: list[dict] | None = None,
) -> None:
    if not await _send_json_if_open(
        websocket,
        {"type": "stage", "name": "received", "message": "已收到你的消息。"}
    ):
        return
    initial_state = build_initial_state(
        session_id=session_id,
        message=message,
        user_profile=user_profile,
        multimodal_features=multimodal_features,
        voice_segments=voice_segments,
    )
    config = {"configurable": {"thread_id": session_id}}

    # 从 astream updates 中累积最终状态，避免 get_state() 在首次运行时的边界问题
    accumulated_state: dict = dict(initial_state)

    async for mode, chunk in compiled_graph.astream(
        initial_state,
        config=config,
        stream_mode=["updates", "custom"],
    ):
        if mode == "updates":
            for node_name, node_output in chunk.items():
                # 将每个节点的输出合并到累积状态
                if isinstance(node_output, dict):
                    accumulated_state.update(node_output)
                stage = SAFE_STAGE_MAP.get(node_name)
                if stage:
                    if not await _send_json_if_open(
                        websocket,
                        {"type": "stage", "name": stage[0], "message": stage[1]},
                    ):
                        return
        elif mode == "custom" and chunk.get("type") == "token":
            if not await _send_json_if_open(websocket, chunk):
                return
            # 让出事件循环，确保每个 token 帧独立发送到浏览器
            await asyncio.sleep(0)

    # 优先从累积状态取值，回退到 checkpoint
    values = accumulated_state
    try:
        snapshot = compiled_graph.get_state(config)
        if snapshot and snapshot.values:
            # 如果 get_state 可用且有 reply，使用它（更完整）
            snap_values = snapshot.values
            if snap_values.get("reply"):
                values = snap_values
    except Exception:
        logger.debug("get_state() fallback failed, using accumulated state.")

    if not await _send_json_if_open(
        websocket,
        {
            "type": "final",
            "reply": values.get("reply", ""),
            "referral_required": values.get("referral_required", False),
            "hotline_card": values.get("hotline_card"),
            "trace_id": values.get("trace_id", initial_state["trace_id"]),
            "trace": build_trace_payload(values),
        }
    ):
        return
    await _send_json_if_open(websocket, {"type": "end"})


def _segment_to_event_payload(segment: VoiceSegmentResult) -> dict:
    return {
        "type": "transcript",
        "text": segment.transcript,
        "segment_id": segment.segment_id,
        "start_ms": segment.start_ms,
        "end_ms": segment.end_ms,
        "duration_ms": segment.duration_ms,
        "acoustic_features": segment.acoustic_features,
    }


def _merge_voice_multimodal_features(
    base_features: dict | None,
    segment: VoiceSegmentResult,
) -> dict:
    features = dict(base_features or {})
    features["voice_acoustic_features"] = segment.acoustic_features
    features["latest_voice_segment"] = segment.to_state_dict()
    return features


def _process_voice_chunk(transcriber: object, raw_chunk: bytes) -> list[VoiceSegmentResult]:
    if hasattr(transcriber, "process_audio_chunk_with_segments"):
        return transcriber.process_audio_chunk_with_segments(raw_chunk)

    transcripts = transcriber.process_audio_chunk(raw_chunk)
    return [
        VoiceSegmentResult(
            segment_id="segment-compat",
            start_ms=0,
            end_ms=0,
            duration_ms=0,
            transcript=text,
            acoustic_features={},
        )
        for text in transcripts
    ]


def _flush_voice_segment(transcriber: object) -> VoiceSegmentResult | None:
    if hasattr(transcriber, "flush_segment"):
        return transcriber.flush_segment()

    transcript = transcriber.flush()
    if not transcript:
        return None
    return VoiceSegmentResult(
        segment_id="segment-compat",
        start_ms=0,
        end_ms=0,
        duration_ms=0,
        transcript=transcript,
        acoustic_features={},
    )


@router.websocket("/ws/chat/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            await _stream_graph_reply(
                websocket=websocket,
                session_id=session_id,
                message=payload.get("message", ""),
                user_profile=payload.get("user_profile", {}),
                multimodal_features=payload.get("multimodal_features", {}),
            )
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("Text WebSocket route failed.")
        await _send_json_if_open(
            websocket,
            {"type": "error", "message": "当前连接暂时不可用，请稍后再试。"}
        )


@router.websocket("/ws/voice-chat/{session_id}")
async def websocket_voice_chat(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()

    # 延迟创建转写器，模型不可用时优雅降级而非崩溃
    transcriber = create_voice_transcriber()
    if transcriber is None:
        await _send_json_if_open(
            websocket,
            {
                "type": "error",
                "message": "语音识别模型暂时不可用，请使用文字输入。",
            },
        )
        # 保持连接但不处理音频，仍可接收文本指令
        try:
            while True:
                try:
                    message = await websocket.receive()
                except RuntimeError as exc:
                    if _is_disconnect_runtime_error(exc):
                        return
                    raise
                if message.get("type") == "websocket.disconnect":
                    return
        except WebSocketDisconnect:
            return
        return

    voice_context = {
        "user_profile": {},
        "multimodal_features": {},
    }

    try:
        while True:
            try:
                message = await websocket.receive()
            except RuntimeError as exc:
                if _is_disconnect_runtime_error(exc):
                    return
                raise

            if message.get("type") == "websocket.disconnect":
                return

            raw_chunk = message.get("bytes")
            if raw_chunk is not None:
                segments = _process_voice_chunk(transcriber, raw_chunk)
                for segment in segments:
                    if not await _send_json_if_open(
                        websocket,
                        _segment_to_event_payload(segment),
                    ):
                        return
                    await _stream_graph_reply(
                        websocket=websocket,
                        session_id=session_id,
                        message=segment.transcript,
                        user_profile=voice_context["user_profile"],
                        multimodal_features=_merge_voice_multimodal_features(
                            voice_context["multimodal_features"],
                            segment,
                        ),
                        voice_segments=[segment.to_state_dict()],
                    )
                continue

            raw_text = message.get("text")
            if not raw_text:
                continue

            payload = json.loads(raw_text)
            voice_context["user_profile"] = payload.get(
                "user_profile", voice_context["user_profile"]
            )
            voice_context["multimodal_features"] = payload.get(
                "multimodal_features", voice_context["multimodal_features"]
            )

            if payload.get("type") == "input_audio_buffer.commit":
                segment = _flush_voice_segment(transcriber)
                if segment:
                    if not await _send_json_if_open(
                        websocket,
                        _segment_to_event_payload(segment),
                    ):
                        return
                    await _stream_graph_reply(
                        websocket=websocket,
                        session_id=session_id,
                        message=segment.transcript,
                        user_profile=voice_context["user_profile"],
                        multimodal_features=_merge_voice_multimodal_features(
                            voice_context["multimodal_features"],
                            segment,
                        ),
                        voice_segments=[segment.to_state_dict()],
                    )
    except WebSocketDisconnect:
        return
    except RuntimeError as exc:
        if _is_disconnect_runtime_error(exc):
            return
        logger.exception("Voice WebSocket route failed.")
        await _send_json_if_open(
            websocket,
            {"type": "error", "message": "语音连接暂时不可用，请稍后再试。"},
        )
    except Exception:
        logger.exception("Voice WebSocket route failed.")
        await _send_json_if_open(
            websocket,
            {"type": "error", "message": "语音连接暂时不可用，请稍后再试。"},
        )
