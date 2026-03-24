"""离线语音识别服务。

安装依赖示例：
    pip install faster-whisper sounddevice webrtcvad numpy

说明：
1. 本模块固定使用本地 faster-whisper CTranslate2 模型。
2. 文件转写与麦克风流式转写共用同一份模型实例，避免重复加载。
3. 实时模式采用 Producer-Consumer 结构：
   - 录音线程负责采集 16kHz、mono 的 PCM 音频并放入 `queue.Queue`
   - 消费端负责做 VAD 聚合，在一句话结束时再触发模型推理
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Generator, Sequence

import numpy as np

from app.services.acoustic_feature_service import AcousticFeatureExtractor

try:
    import ctranslate2
except ImportError:  # pragma: no cover - 依赖缺失时在运行阶段再给出明确报错
    ctranslate2 = None

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover - 依赖缺失时在运行阶段再给出明确报错
    sd = None

try:
    import webrtcvad
except ImportError:  # pragma: no cover - 依赖缺失时在运行阶段再给出明确报错
    webrtcvad = None

try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover - 依赖缺失时在运行阶段再给出明确报错
    WhisperModel = None

logger = logging.getLogger(__name__)

DEFAULT_WHISPER_MODEL_PATH = Path(
    "/media/chai/Data/Linux_AI_Resources/modelscope/hub/models/"
    "Tiandong/faster-whisper-large-v3-turbo-ct2"
)


@dataclass(slots=True)
class WhisperSegment:
    """统一的分段识别结果。"""

    start: float
    end: float
    text: str


@dataclass(slots=True)
class SpeechBufferState:
    """实时流式识别时的语音缓冲状态。"""

    speech_frames: list[np.ndarray] = field(default_factory=list)
    speech_started: bool = False
    trailing_silence_frames: int = 0
    segment_start_ms: int | None = None
    last_speech_end_ms: int | None = None
    speech_frame_count: int = 0
    current_pause_frames: int = 0
    pause_durations_ms: list[int] = field(default_factory=list)

    def reset(self) -> None:
        """重置本轮语音缓冲。"""

        self.speech_frames.clear()
        self.speech_started = False
        self.trailing_silence_frames = 0
        self.segment_start_ms = None
        self.last_speech_end_ms = None
        self.speech_frame_count = 0
        self.current_pause_frames = 0
        self.pause_durations_ms.clear()


@dataclass(slots=True)
class VoiceSegmentResult:
    """VAD 切分后的结构化片段。"""

    segment_id: str
    start_ms: int
    end_ms: int
    duration_ms: int
    transcript: str
    acoustic_features: dict[str, Any]

    def to_state_dict(self) -> dict[str, Any]:
        return asdict(self)


class FasterWhisperASRService:
    """本地 faster-whisper 语音识别服务。

    设计目标：
    - 模型实例只加载一次
    - 自动在 CUDA 和 CPU 间切换
    - 对文件输入与 numpy 音频输入提供统一接口
    - 在异常情况下给出明确错误信息，便于上层 Agent 与 WebSocket 层处理
    """

    def __init__(
        self,
        model_path: str | Path = DEFAULT_WHISPER_MODEL_PATH,
        device: str | None = None,
        compute_type: str | None = None,
        language: str = "zh",
        beam_size: int = 1,
        vad_filter: bool = True,
        vad_parameters: dict[str, Any] | None = None,
        model: Any | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.language = language
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.vad_parameters = vad_parameters or {
            "min_silence_duration_ms": 350,
            "speech_pad_ms": 120,
        }

        detected_device, detected_compute_type = self.select_runtime()
        self.device = device or detected_device
        self.compute_type = compute_type or detected_compute_type
        self.model = model or self._load_model()

    @staticmethod
    def detect_cuda_available() -> bool:
        """检测是否存在可用 CUDA 设备。"""

        if ctranslate2 is None:
            return False
        try:
            return ctranslate2.get_cuda_device_count() > 0
        except Exception:
            return False

    @classmethod
    def select_runtime(cls, has_cuda: bool | None = None) -> tuple[str, str]:
        """根据硬件环境选择运行设备和计算精度。"""

        cuda_available = cls.detect_cuda_available() if has_cuda is None else has_cuda
        if cuda_available:
            return "cuda", "float16"
        return "cpu", "int8"

    @staticmethod
    def build_transcription_result(
        segments: Sequence[WhisperSegment],
    ) -> tuple[str, list[dict[str, float | str]]]:
        """将分段结果拼接为上层业务更易使用的结构。"""

        cleaned_segments = [
            {"start": round(segment.start, 3), "end": round(segment.end, 3), "text": segment.text.strip()}
            for segment in segments
            if segment.text.strip()
        ]
        full_text = " ".join(item["text"] for item in cleaned_segments).strip()
        return full_text, cleaned_segments

    @staticmethod
    def should_flush_buffer(
        state: SpeechBufferState,
        silence_frame_threshold: int,
    ) -> bool:
        """根据 VAD 结果判断是否应结束本句话并触发推理。"""

        return (
            state.speech_started
            and bool(state.speech_frames)
            and state.trailing_silence_frames >= silence_frame_threshold
        )

    def _ensure_runtime_dependencies(self) -> None:
        if WhisperModel is None:
            raise RuntimeError(
                "未安装 faster-whisper。请先执行: pip install faster-whisper"
            )

    def _load_model(self) -> Any:
        """加载本地 Whisper 模型。

        如果初次尝试使用 CUDA 发生显存不足，会自动回退到 CPU int8。
        """

        self._ensure_runtime_dependencies()
        if not self.model_path.exists():
            raise FileNotFoundError(f"未找到本地 Whisper 模型目录: {self.model_path}")

        try:
            logger.info(
                "Loading faster-whisper model from %s on %s (%s)",
                self.model_path,
                self.device,
                self.compute_type,
            )
            return WhisperModel(
                str(self.model_path),
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=max(1, os.cpu_count() or 4),
                num_workers=1,
            )
        except Exception as exc:
            if self.device == "cuda" and self._is_cuda_oom_error(exc):
                logger.warning("CUDA 显存不足，自动回退到 CPU int8 模式。")
                self.device = "cpu"
                self.compute_type = "int8"
                return WhisperModel(
                    str(self.model_path),
                    device=self.device,
                    compute_type=self.compute_type,
                    cpu_threads=max(1, os.cpu_count() or 4),
                    num_workers=1,
                )
            raise RuntimeError(f"加载 Whisper 模型失败: {exc}") from exc

    @staticmethod
    def _is_cuda_oom_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "out of memory" in message or "cuda" in message and "memory" in message

    @staticmethod
    def _prepare_audio_array(audio_array: np.ndarray) -> np.ndarray:
        """将任意单通道/双通道 numpy 音频转成 whisper 可接受的 float32 单通道数据。"""

        if audio_array.ndim == 2:
            audio_array = audio_array.mean(axis=1)
        if audio_array.ndim != 1:
            raise ValueError("音频数组必须为一维单通道或二维双通道。")

        if np.issubdtype(audio_array.dtype, np.integer):
            info = np.iinfo(audio_array.dtype)
            scale = max(abs(info.min), info.max) or 1
            audio_array = audio_array.astype(np.float32) / float(scale)
        else:
            audio_array = audio_array.astype(np.float32)

        return np.ascontiguousarray(np.clip(audio_array, -1.0, 1.0))

    def _transcribe_once(
        self,
        audio_input: str | np.ndarray,
    ) -> tuple[str, list[dict[str, float | str]]]:
        segments_iterable, _ = self.model.transcribe(
            audio_input,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            vad_parameters=self.vad_parameters,
            condition_on_previous_text=False,
            word_timestamps=False,
            temperature=0.0,
        )
        segments = [
            WhisperSegment(
                start=float(segment.start),
                end=float(segment.end),
                text=str(segment.text).strip(),
            )
            for segment in segments_iterable
        ]
        return self.build_transcription_result(segments)

    def transcribe_audio(
        self,
        audio_path_or_array: str | Path | np.ndarray,
    ) -> tuple[str, list[dict[str, float | str]]]:
        """执行一次完整转写。

        参数：
        - `audio_path_or_array`: 可以是本地音频文件路径，也可以是 16kHz PCM/float 的 numpy 数组。

        返回：
        - `full_text`: 拼接后的整句文本
        - `segments`: 带时间戳的分段结果
        """

        try:
            if isinstance(audio_path_or_array, (str, Path)):
                audio_path = Path(audio_path_or_array)
                if not audio_path.exists():
                    raise FileNotFoundError(f"未找到音频文件: {audio_path}")
                audio_input: str | np.ndarray = str(audio_path)
            elif isinstance(audio_path_or_array, np.ndarray):
                audio_input = self._prepare_audio_array(audio_path_or_array)
            else:
                raise TypeError("audio_path_or_array 必须是文件路径或 numpy.ndarray。")

            return self._transcribe_once(audio_input)
        except FileNotFoundError:
            raise
        except ValueError as exc:
            raise ValueError(f"输入音频格式无效: {exc}") from exc
        except RuntimeError as exc:
            if self.device == "cuda" and self._is_cuda_oom_error(exc):
                logger.warning("推理阶段显存不足，切换到 CPU int8 重试一次。")
                self.device = "cpu"
                self.compute_type = "int8"
                self.model = self._load_model()
                return self.transcribe_audio(audio_path_or_array)
            raise RuntimeError(f"Whisper 推理失败: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"音频转写失败，请检查输入文件与依赖环境: {exc}") from exc


class PCMChunkAudioTranscriber:
    """面向 WebSocket 二进制音频块的实时转写适配器。

    职责：
    - 接收浏览器持续发送的 raw PCM int16 bytes
    - 切分成 WebRTC VAD 需要的固定时长帧
    - 复用现有句级缓冲与 faster-whisper 推理逻辑
    """

    def __init__(
        self,
        asr_service: FasterWhisperASRService,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        vad_mode: int = 2,
        silence_duration_ms: int = 600,
        vad: Any | None = None,
        feature_extractor: AcousticFeatureExtractor | None = None,
    ) -> None:
        self.asr_service = asr_service
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.vad_mode = vad_mode
        self.silence_duration_ms = silence_duration_ms
        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)
        self.frame_bytes = self.frame_size * np.dtype(np.int16).itemsize
        self.silence_frame_threshold = max(1, self.silence_duration_ms // self.frame_duration_ms)
        self.state = SpeechBufferState()
        self._pending_bytes = bytearray()
        self._processed_frames = 0
        self._segment_counter = 0
        self.feature_extractor = feature_extractor or AcousticFeatureExtractor(
            sample_rate=self.sample_rate,
            frame_duration_ms=self.frame_duration_ms,
        )

        if vad is not None:
            self.vad = vad
        else:
            self._ensure_runtime_dependencies()
            self.vad = webrtcvad.Vad(self.vad_mode)

    def _ensure_runtime_dependencies(self) -> None:
        if webrtcvad is None:
            raise RuntimeError(
                "未安装 webrtcvad。请先执行: pip install webrtcvad"
            )

    @staticmethod
    def _frame_to_pcm(frame_bytes: bytes) -> np.ndarray:
        normalized = frame_bytes[:-1] if len(frame_bytes) % 2 else frame_bytes
        if not normalized:
            return np.array([], dtype=np.int16)
        return np.frombuffer(normalized, dtype=np.int16).copy()

    def _flush_current_utterance(
        self,
        callback: Callable[[str], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> VoiceSegmentResult | None:
        if not self.state.speech_frames:
            return None

        if status_callback:
            status_callback("transcribing")

        start_ms = int(self.state.segment_start_ms or 0)
        end_ms = int(self.state.last_speech_end_ms or start_ms)
        duration_ms = max(0, end_ms - start_ms)
        pause_durations_ms = list(self.state.pause_durations_ms)
        voiced_duration_ms = self.state.speech_frame_count * self.frame_duration_ms
        utterance_pcm = np.concatenate(self.state.speech_frames, axis=0)
        self.state.reset()

        try:
            text, _ = self.asr_service.transcribe_audio(utterance_pcm)
        except Exception as exc:
            logger.exception("PCM chunk ASR failed: %s", exc)
            if status_callback:
                status_callback("error")
            return None

        try:
            acoustic_features = self.feature_extractor.extract_features(
                utterance_pcm,
                pause_durations_ms=pause_durations_ms,
                voiced_duration_ms=voiced_duration_ms,
                segment_duration_ms=duration_ms,
            )
        except Exception as exc:
            logger.exception("Acoustic feature extraction failed: %s", exc)
            acoustic_features = self.feature_extractor.extract_features(
                np.array([], dtype=np.int16)
            )

        if text and callback:
            callback(text)
        self._segment_counter += 1
        return VoiceSegmentResult(
            segment_id=f"segment-{self._segment_counter:06d}",
            start_ms=start_ms,
            end_ms=end_ms,
            duration_ms=duration_ms,
            transcript=text,
            acoustic_features=acoustic_features,
        )

    def _consume_frame(
        self,
        frame_bytes: bytes,
        callback: Callable[[str], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> VoiceSegmentResult | None:
        if not frame_bytes:
            return None

        is_speech = self.vad.is_speech(frame_bytes, self.sample_rate)
        pcm_frame = self._frame_to_pcm(frame_bytes)
        if pcm_frame.size == 0:
            return None

        frame_start_ms = self._processed_frames * self.frame_duration_ms
        frame_end_ms = frame_start_ms + self.frame_duration_ms

        if is_speech:
            if not self.state.speech_started and status_callback:
                status_callback("listening")
            if not self.state.speech_started:
                self.state.segment_start_ms = frame_start_ms
            elif self.state.current_pause_frames > 0:
                self.state.pause_durations_ms.append(
                    self.state.current_pause_frames * self.frame_duration_ms
                )
                self.state.current_pause_frames = 0
            self.state.speech_started = True
            self.state.trailing_silence_frames = 0
            self.state.speech_frame_count += 1
            self.state.last_speech_end_ms = frame_end_ms
            self.state.speech_frames.append(pcm_frame)
            return None

        if self.state.speech_started:
            self.state.trailing_silence_frames += 1
            self.state.current_pause_frames += 1
            if self.state.trailing_silence_frames <= self.silence_frame_threshold:
                self.state.speech_frames.append(pcm_frame)

            if FasterWhisperASRService.should_flush_buffer(
                state=self.state,
                silence_frame_threshold=self.silence_frame_threshold,
            ):
                return self._flush_current_utterance(
                    callback=callback,
                    status_callback=status_callback,
                )
        return None

    def _advance_frame_clock(self) -> None:
        self._processed_frames += 1

    def process_audio_chunk_with_segments(
        self,
        chunk: bytes,
        callback: Callable[[str], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> list[VoiceSegmentResult]:
        if not chunk:
            return []

        self._pending_bytes.extend(chunk)
        utterances: list[VoiceSegmentResult] = []

        while len(self._pending_bytes) >= self.frame_bytes:
            frame_bytes = bytes(self._pending_bytes[: self.frame_bytes])
            del self._pending_bytes[: self.frame_bytes]
            segment = self._consume_frame(
                frame_bytes,
                callback=callback,
                status_callback=status_callback,
            )
            self._advance_frame_clock()
            if segment:
                utterances.append(segment)

        return utterances

    def process_audio_chunk(
        self,
        chunk: bytes,
        callback: Callable[[str], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> list[str]:
        segments = self.process_audio_chunk_with_segments(
            chunk,
            callback=callback,
            status_callback=status_callback,
        )
        return [segment.transcript for segment in segments if segment.transcript]

    def flush_segment(
        self,
        callback: Callable[[str], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> VoiceSegmentResult | None:
        pending_samples = 0
        if self._pending_bytes and self.state.speech_started:
            pcm_frame = self._frame_to_pcm(bytes(self._pending_bytes))
            if pcm_frame.size:
                self.state.speech_frames.append(pcm_frame)
                pending_samples = int(pcm_frame.size)
        self._pending_bytes.clear()

        if pending_samples and self.state.segment_start_ms is None:
            self.state.segment_start_ms = self._processed_frames * self.frame_duration_ms
        if pending_samples:
            self.state.last_speech_end_ms = int(
                round(
                    (self._processed_frames * self.frame_size + pending_samples)
                    * 1000
                    / self.sample_rate
                )
            )

        return self._flush_current_utterance(
            callback=callback,
            status_callback=status_callback,
        )

    def flush(
        self,
        callback: Callable[[str], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> str:
        segment = self.flush_segment(
            callback=callback,
            status_callback=status_callback,
        )
        return segment.transcript if segment else ""


class MicrophoneStreamTranscriber:
    """麦克风实时转写控制器。

    使用后台线程采集音频，再在消费侧做语音起止检测与句级推理。
    这样既能避免主线程被录音阻塞，也能避免每一小帧都触发一次 ASR。
    """

    def __init__(
        self,
        asr_service: FasterWhisperASRService,
        sample_rate: int = 16000,
        channels: int = 1,
        frame_duration_ms: int = 30,
        vad_mode: int = 2,
        silence_duration_ms: int = 600,
        queue_maxsize: int = 256,
    ) -> None:
        self.asr_service = asr_service
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_duration_ms = frame_duration_ms
        self.vad_mode = vad_mode
        self.silence_duration_ms = silence_duration_ms
        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)
        self.silence_frame_threshold = max(1, self.silence_duration_ms // self.frame_duration_ms)
        self.audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=queue_maxsize)
        self.stop_event = threading.Event()
        self.recording_thread: threading.Thread | None = None
        self._stream_error: Exception | None = None

        self._ensure_runtime_dependencies()
        self.vad = webrtcvad.Vad(self.vad_mode)

    def _ensure_runtime_dependencies(self) -> None:
        if sd is None:
            raise RuntimeError(
                "未安装 sounddevice。请先执行: pip install sounddevice"
            )
        if webrtcvad is None:
            raise RuntimeError(
                "未安装 webrtcvad。请先执行: pip install webrtcvad"
            )

    def _audio_callback(
        self,
        indata: bytes,
        frames: int,
        time_info: dict[str, Any],
        status: Any,
    ) -> None:
        """sounddevice 回调。

        回调运行在音频线程中，因此这里只做极轻量的队列投递。
        """

        del time_info
        if status:
            logger.warning("Microphone status: %s", status)

        frame_bytes = bytes(indata)
        if not frame_bytes:
            return

        try:
            self.audio_queue.put_nowait(frame_bytes)
        except queue.Full:
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.audio_queue.put_nowait(frame_bytes)
            except queue.Full:
                logger.warning("Audio queue is full, dropping frame.")

    def _record_audio_loop(self) -> None:
        """后台录音线程。"""

        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.frame_size,
                channels=self.channels,
                dtype="int16",
                callback=self._audio_callback,
            ):
                while not self.stop_event.is_set():
                    time.sleep(0.05)
        except Exception as exc:
            self._stream_error = exc
            self.stop_event.set()

    def start(self) -> None:
        """启动后台录音线程。"""

        if self.recording_thread and self.recording_thread.is_alive():
            return
        self.stop_event.clear()
        self._stream_error = None
        self.recording_thread = threading.Thread(
            target=self._record_audio_loop,
            name="microphone-producer",
            daemon=True,
        )
        self.recording_thread.start()

    def stop(self) -> None:
        """停止录音线程。"""

        self.stop_event.set()
        if self.recording_thread and self.recording_thread.is_alive():
            self.recording_thread.join(timeout=2.0)
        self.recording_thread = None

    @staticmethod
    def _frame_to_pcm(frame_bytes: bytes) -> np.ndarray:
        return np.frombuffer(frame_bytes, dtype=np.int16).copy()

    def _flush_current_utterance(
        self,
        state: SpeechBufferState,
        callback: Callable[[str], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> str:
        """将当前语音缓冲送入 ASR 推理。"""

        if not state.speech_frames:
            return ""

        if status_callback:
            status_callback("transcribing")

        utterance_pcm = np.concatenate(state.speech_frames, axis=0)
        state.reset()

        try:
            text, _ = self.asr_service.transcribe_audio(utterance_pcm)
        except Exception as exc:
            logger.exception("Realtime ASR failed: %s", exc)
            if status_callback:
                status_callback("error")
            return ""

        if text and callback:
            callback(text)
        return text

    def stream_transcriptions(
        self,
        callback: Callable[[str], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> Generator[str, None, None]:
        """持续监听麦克风，并在一句话结束时 yield 文本。

        说明：
        - 当检测到说话起点时，触发 `status_callback("listening")`
        - 当检测到静音收尾并开始推理时，触发 `status_callback("transcribing")`
        - 当出现异常时，触发 `status_callback("error")`
        """

        state = SpeechBufferState()
        self.start()

        try:
            while not self.stop_event.is_set():
                if self._stream_error is not None:
                    raise RuntimeError(f"麦克风采集失败: {self._stream_error}")

                try:
                    frame_bytes = self.audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                is_speech = self.vad.is_speech(frame_bytes, self.sample_rate)
                pcm_frame = self._frame_to_pcm(frame_bytes)

                if is_speech:
                    if not state.speech_started and status_callback:
                        status_callback("listening")
                    state.speech_started = True
                    state.trailing_silence_frames = 0
                    state.speech_frames.append(pcm_frame)
                    continue

                if state.speech_started:
                    state.trailing_silence_frames += 1
                    if state.trailing_silence_frames <= self.silence_frame_threshold:
                        state.speech_frames.append(pcm_frame)

                    if self.asr_service.should_flush_buffer(
                        state=state,
                        silence_frame_threshold=self.silence_frame_threshold,
                    ):
                        text = self._flush_current_utterance(
                            state=state,
                            callback=callback,
                            status_callback=status_callback,
                        )
                        if text:
                            yield text
        except KeyboardInterrupt:
            logger.info("Microphone transcription interrupted by user.")
        finally:
            if state.speech_frames:
                text = self._flush_current_utterance(
                    state=state,
                    callback=callback,
                    status_callback=status_callback,
                )
                if text:
                    yield text
            self.stop()


def _build_demo_status_printer() -> Callable[[str], None]:
    """构建一个适合控制台联调的状态打印器。"""

    def _printer(status: str) -> None:
        if status == "listening":
            print("Listening...")
        elif status == "transcribing":
            print("Transcribing...")
        elif status == "error":
            print("ASR error occurred. Please check logs.")

    return _printer


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    parser = argparse.ArgumentParser(description="Local faster-whisper ASR demo")
    parser.add_argument(
        "--audio",
        type=str,
        default="",
        help="本地测试音频路径。若不提供，则进入麦克风实时转写模式。",
    )
    args = parser.parse_args()

    service = FasterWhisperASRService()

    if args.audio:
        print("Transcribing...")
        text, segments = service.transcribe_audio(args.audio)
        print("Result:", text or "<empty>")
        print("Segments:", segments)
    else:
        print("Microphone mode started. Press Ctrl+C to stop.")
        transcriber = MicrophoneStreamTranscriber(service)
        status_printer = _build_demo_status_printer()
        for utterance in transcriber.stream_transcriptions(status_callback=status_printer):
            print("Result:", utterance)
