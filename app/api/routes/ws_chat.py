"""WebSocket 聊天接口。

协议设计：
- {"type":"stage","name":"received","message":"..."}
- {"type":"stage","name":"rag_retriever_done","message":"..."}
- {"type":"token","chunk":"我"}
- {"type":"tts_audio","segment_id":"tts-0001","payload":"<base64>"}
- {"type":"tts_end","segment_id":"tts-0001","text":"先深呼吸。"}
- {"type":"risk_event","alert_event_id":"...","risk_level":"high",...}
- {"type":"final","reply":"...", "risk_level":"low", "alert_status": {}, "alert_event_id": null, ...}
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

from app.core.config import get_settings
from app.graph.workflow import get_compiled_graph
from app.services.asr_service import (
    PCMChunkAudioTranscriber,
    FasterWhisperASRService,
    VoiceSegmentResult,
)
from app.models.face_segment import FaceSegment
from app.services.emotion2vec_service import (
    build_emotion2vec_reading,
    get_emotion2vec_service,
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


def _build_risk_event_payload(values: dict) -> dict | None:
    if values.get("risk_level") != "high" or not values.get("alert_event_id"):
        return None

    alert_status = values.get("alert_status") or {}
    return {
        "type": "risk_event",
        "alert_event_id": values.get("alert_event_id"),
        "risk_level": values.get("risk_level"),
        "handler_status": alert_status.get("handler_status", "created"),
        "delivery_status": alert_status.get("delivery_status", "created"),
        "trace_id": values.get("trace_id"),
        "masked_session_id": alert_status.get("masked_session_id"),
        "summary": alert_status.get(
            "summary",
            "检测到需要人工关注的高风险心理支持对话，请尽快复核。",
        ),
    }


def _build_final_payload(values: dict, initial_state: dict) -> dict:
    return {
        "type": "final",
        "reply": values.get("reply", ""),
        "risk_level": values.get("risk_level", "low"),
        "referral_required": values.get("referral_required", False),
        "hotline_card": values.get("hotline_card"),
        "alert_status": values.get("alert_status", {}),
        "alert_event_id": values.get("alert_event_id"),
        "trace_id": values.get("trace_id", initial_state["trace_id"]),
        "trace": build_trace_payload(values),
    }


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
    face_segments: list[dict] | None = None,
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
        face_segments=face_segments,
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
        elif mode == "custom" and chunk.get("type") in {"token", "tts_audio", "tts_end"}:
            if not await _send_json_if_open(websocket, chunk):
                return
            # 让出事件循环，确保每个自定义事件帧独立发送到浏览器
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

    risk_event_payload = _build_risk_event_payload(values)
    if risk_event_payload and not await _send_json_if_open(
        websocket,
        risk_event_payload,
    ):
        return

    if not await _send_json_if_open(
        websocket,
        _build_final_payload(values, initial_state),
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


def _normalize_transcript_text(text: str | None) -> str:
    return text.strip() if isinstance(text, str) else ""


async def _dispatch_voice_segment(
    websocket: WebSocket,
    session_id: str,
    segment: VoiceSegmentResult,
    voice_context: dict,
    emotion2vec_reading: dict | None = None,
) -> bool:
    transcript = _normalize_transcript_text(getattr(segment, "transcript", ""))
    if not transcript:
        logger.debug(
            "Skipping empty voice transcript segment_id=%s",
            getattr(segment, "segment_id", "unknown"),
        )
        return False

    segment.transcript = transcript

    if not await _send_json_if_open(
        websocket,
        _segment_to_event_payload(segment),
    ):
        return False

    face_segs = list(voice_context["face_segments"])
    voice_context["face_segments"] = []

    await _stream_graph_reply(
        websocket=websocket,
        session_id=session_id,
        message=segment.transcript,
        user_profile=voice_context["user_profile"],
        multimodal_features=_merge_voice_multimodal_features(
            voice_context["multimodal_features"],
            segment,
            emotion2vec_reading=emotion2vec_reading,
        ),
        voice_segments=[
            _build_voice_segment_state(
                segment,
                emotion2vec_reading=emotion2vec_reading,
            )
        ],
        face_segments=face_segs,
    )
    return True


def _build_voice_segment_state(
    segment: VoiceSegmentResult,
    emotion2vec_reading: dict | None = None,
) -> dict:
    segment_state = segment.to_state_dict()
    if emotion2vec_reading is not None:
        segment_state["emotion2vec_reading"] = emotion2vec_reading
    return segment_state


def _merge_voice_multimodal_features(
    base_features: dict | None,
    segment: VoiceSegmentResult,
    emotion2vec_reading: dict | None = None,
) -> dict:
    features = dict(base_features or {})
    features["voice_acoustic_features"] = segment.acoustic_features
    features["latest_voice_segment"] = segment.to_state_dict()
    if emotion2vec_reading is not None:
        features["emotion2vec_reading"] = emotion2vec_reading
    return features


async def _analyze_emotion2vec_for_segment(
    segment: VoiceSegmentResult,
) -> dict[str, object]:
    settings = get_settings()

    if not settings.enable_emotion2vec:
        return build_emotion2vec_reading(
            status="disabled",
            model_dir=settings.emotion2vec_model_dir or None,
        )

    audio_pcm = getattr(segment, "audio_pcm", None)
    if audio_pcm is None:
        return build_emotion2vec_reading(
            status="unavailable",
            model_dir=settings.emotion2vec_model_dir or None,
            error="Raw audio unavailable for emotion2vec inference.",
        )

    try:
        service = get_emotion2vec_service(settings)
        return await asyncio.to_thread(service.analyze, audio_pcm)
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.warning("Emotion2Vec segment inference failed unexpectedly: %s", exc)
        return build_emotion2vec_reading(
            status="error",
            model_dir=settings.emotion2vec_model_dir or None,
            error=str(exc),
        )


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


def _parse_face_segments(raw_segments: list | None) -> list[dict]:
    """校验并解析前端传来的 face_segments 列表。

    每个元素通过 FaceSegment Pydantic 模型进行结构校验，
    无效条目会被静默跳过以保证鲁棒性。
    """
    if not raw_segments:
        return []
    validated: list[dict] = []
    for item in raw_segments:
        try:
            segment = FaceSegment.model_validate(item)
            validated.append(segment.model_dump())
        except Exception:
            logger.debug("Skipping invalid face_segment payload: %s", item)
    return validated


@router.websocket("/ws/chat/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            face_segments = _parse_face_segments(
                payload.get("face_segments")
            )
            await _stream_graph_reply(
                websocket=websocket,
                session_id=session_id,
                message=payload.get("message", ""),
                user_profile=payload.get("user_profile", {}),
                multimodal_features=payload.get("multimodal_features", {}),
                face_segments=face_segments,
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

    voice_context: dict = {
        "user_profile": {},
        "multimodal_features": {},
        "face_segments": [],
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
                    emotion2vec_reading = await _analyze_emotion2vec_for_segment(segment)
                    if not await _dispatch_voice_segment(
                        websocket=websocket,
                        session_id=session_id,
                        segment=segment,
                        voice_context=voice_context,
                        emotion2vec_reading=emotion2vec_reading,
                    ) and _websocket_is_closed(websocket):
                        return
                continue

            raw_text = message.get("text")
            if not raw_text:
                continue

            payload = json.loads(raw_text)

            # 面部特征帧：前端 1–1.5s 滑动窗口聚合后推送
            if payload.get("type") == "face_segment":
                try:
                    seg = FaceSegment.model_validate(payload.get("data", {}))
                    voice_context["face_segments"].append(seg.model_dump())
                except Exception:
                    logger.debug("Skipping invalid face_segment in voice WS: %s", payload)
                continue

            voice_context["user_profile"] = payload.get(
                "user_profile", voice_context["user_profile"]
            )
            voice_context["multimodal_features"] = payload.get(
                "multimodal_features", voice_context["multimodal_features"]
            )

            if payload.get("type") == "input_audio_buffer.commit":
                segment = _flush_voice_segment(transcriber)
                if segment:
                    emotion2vec_reading = await _analyze_emotion2vec_for_segment(segment)
                    if not await _dispatch_voice_segment(
                        websocket=websocket,
                        session_id=session_id,
                        segment=segment,
                        voice_context=voice_context,
                        emotion2vec_reading=emotion2vec_reading,
                    ) and _websocket_is_closed(websocket):
                        return
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
