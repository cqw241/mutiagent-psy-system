import numpy as np

from app.services.asr_service import (
    PCMChunkAudioTranscriber,
    FasterWhisperASRService,
    SpeechBufferState,
    VoiceSegmentResult,
    WhisperSegment,
)


def test_select_runtime_prefers_cuda_when_available():
    device, compute_type = FasterWhisperASRService.select_runtime(has_cuda=True)
    assert device == "cuda"
    assert compute_type == "float16"


def test_select_runtime_falls_back_to_cpu():
    device, compute_type = FasterWhisperASRService.select_runtime(has_cuda=False)
    assert device == "cpu"
    assert compute_type == "int8"


def test_build_transcription_result_merges_text_and_segments():
    raw_segments = [
        WhisperSegment(start=0.0, end=1.2, text="我最近有点难受"),
        WhisperSegment(start=1.3, end=2.8, text="晚上睡不好"),
    ]

    text, segments = FasterWhisperASRService.build_transcription_result(raw_segments)

    assert text == "我最近有点难受 晚上睡不好"
    assert segments == [
        {"start": 0.0, "end": 1.2, "text": "我最近有点难受"},
        {"start": 1.3, "end": 2.8, "text": "晚上睡不好"},
    ]


def test_should_flush_buffer_requires_voice_and_silence_tail():
    state = SpeechBufferState(
        speech_frames=[np.ones(160, dtype=np.int16)],
        speech_started=True,
        trailing_silence_frames=12,
    )

    assert FasterWhisperASRService.should_flush_buffer(
        state=state,
        silence_frame_threshold=10,
    )


def test_should_not_flush_when_no_speech_detected():
    state = SpeechBufferState(
        speech_frames=[],
        speech_started=False,
        trailing_silence_frames=20,
    )

    assert not FasterWhisperASRService.should_flush_buffer(
        state=state,
        silence_frame_threshold=10,
    )


class _FakeVad:
    def __init__(self, decisions):
        self._decisions = iter(decisions)

    def is_speech(self, frame_bytes, sample_rate):
        assert sample_rate == 16000
        assert frame_bytes
        return next(self._decisions)


class _StubASRService:
    def __init__(self):
        self.calls = []

    def transcribe_audio(self, audio_array):
        self.calls.append(audio_array.copy())
        return ("识别完成", [{"start": 0.0, "end": 0.3, "text": "识别完成"}])


def _pcm_frame(value: int, samples: int = 480) -> bytes:
    return np.full(samples, value, dtype=np.int16).tobytes()


def test_pcm_chunk_audio_transcriber_flushes_after_silence_threshold():
    asr_service = _StubASRService()
    transcriber = PCMChunkAudioTranscriber(
        asr_service=asr_service,
        vad=_FakeVad([True, True, False, False]),
        silence_duration_ms=60,
    )

    payload = _pcm_frame(10) + _pcm_frame(20) + _pcm_frame(0) + _pcm_frame(0)

    assert transcriber.process_audio_chunk(payload[:1200]) == []
    assert transcriber.process_audio_chunk(payload[1200:2500]) == []

    results = transcriber.process_audio_chunk(payload[2500:])

    assert results == ["识别完成"]
    assert len(asr_service.calls) == 1
    assert asr_service.calls[0].dtype == np.int16
    assert asr_service.calls[0].shape[0] == 480 * 4


def test_pcm_chunk_audio_transcriber_returns_segment_metadata():
    asr_service = _StubASRService()
    transcriber = PCMChunkAudioTranscriber(
        asr_service=asr_service,
        vad=_FakeVad([True, True, False, False]),
        silence_duration_ms=60,
    )

    payload = _pcm_frame(10) + _pcm_frame(20) + _pcm_frame(0) + _pcm_frame(0)

    segments = transcriber.process_audio_chunk_with_segments(payload)

    assert len(segments) == 1
    segment = segments[0]
    assert segment.segment_id.startswith("segment-")
    assert segment.start_ms == 0
    assert segment.end_ms == 60
    assert segment.duration_ms == 60
    assert segment.transcript == "识别完成"
    assert "energy_mean" in segment.acoustic_features
    assert "speech_ratio" in segment.acoustic_features


def test_voice_segment_state_dict_hides_audio_by_default():
    segment = VoiceSegmentResult(
        segment_id="segment-000001",
        start_ms=0,
        end_ms=420,
        duration_ms=420,
        transcript="识别完成",
        acoustic_features={"energy_mean": 0.1},
        audio_pcm=np.array([1, 2, 3], dtype=np.int16),
    )

    public_state = segment.to_state_dict()
    internal_state = segment.to_state_dict(include_audio=True)

    assert "audio_pcm" not in public_state
    assert internal_state["audio_pcm"].tolist() == [1, 2, 3]


def test_pcm_chunk_audio_transcriber_flushes_remaining_audio_on_commit():
    asr_service = _StubASRService()
    transcriber = PCMChunkAudioTranscriber(
        asr_service=asr_service,
        vad=_FakeVad([True]),
        silence_duration_ms=300,
    )

    payload = _pcm_frame(12) + _pcm_frame(14, samples=160)

    assert transcriber.process_audio_chunk(payload) == []

    result = transcriber.flush()

    assert result == "识别完成"
    assert len(asr_service.calls) == 1
    assert asr_service.calls[0].shape[0] == 480 + 160
