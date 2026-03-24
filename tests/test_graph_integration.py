import asyncio

from app.core.config import get_settings
from app.graph.workflow import build_graph


def _make_initial_state(message: str, **overrides) -> dict:
    """构建测试用初始 state，兼容新多智能体架构。"""
    state = {
        "session_id": overrides.get("session_id", "sess-1"),
        "chat_history": [{"role": "user", "content": message}],
        "multimodal_features": overrides.get("multimodal_features", {}),
        "voice_segments": overrides.get("voice_segments", []),
        "has_voice": overrides.get("has_voice", False),
        "has_face": overrides.get("has_face", False),
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {},
        "text_signals": {},
        "voice_signals": {},
        "face_signals": {},
        "reference_context": "",
        "risk_level": "low",
        "referral_required": False,
        "reply": "",
        "trace_id": overrides.get("trace_id", "trace-1"),
        "user_profile": {},
        "alert_status": {},
        "trace": {},
        "hotline_card": None,
    }
    state.update(overrides)
    return state


def _set_emotion2vec_env(monkeypatch, **env):
    managed_keys = {
        "ENABLE_EMOTION2VEC",
        "EMOTION2VEC_MODEL_DIR",
        "EMOTION2VEC_SAMPLE_RATE",
    }
    for key in managed_keys:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def test_full_graph_run_returns_reply():
    graph = build_graph()
    result = asyncio.run(
        graph.ainvoke(
            _make_initial_state("我最近很痛苦", multimodal_features={"facial_emotion": "sad"}),
            config={"configurable": {"thread_id": "sess-1"}},
        )
    )
    assert result["reply"]


def test_graph_persists_chat_history_for_same_thread():
    graph = build_graph()
    config = {"configurable": {"thread_id": "session-memory-demo"}}

    asyncio.run(
        graph.ainvoke(
            _make_initial_state("第一次对话", session_id="session-memory-demo", trace_id="trace-1"),
            config=config,
        )
    )
    asyncio.run(
        graph.ainvoke(
            _make_initial_state("第二次对话", session_id="session-memory-demo", trace_id="trace-2"),
            config=config,
        )
    )

    state_snapshot = graph.get_state(config)
    assert len(state_snapshot.values["chat_history"]) >= 4


def test_graph_can_recover_from_prior_high_risk_turn_in_same_thread():
    graph = build_graph()
    config = {"configurable": {"thread_id": "session-recovery-demo"}}

    first_result = asyncio.run(
        graph.ainvoke(
            _make_initial_state(
                "我不想活了",
                session_id="session-recovery-demo",
                trace_id="trace-risk",
            ),
            config=config,
        )
    )
    assert first_result["referral_required"] is True

    second_result = asyncio.run(
        graph.ainvoke(
            _make_initial_state(
                "我现在心情好起来了，你能陪我聊天吗？",
                session_id="session-recovery-demo",
                trace_id="trace-safe",
            ),
            config=config,
        )
    )

    assert second_result["referral_required"] is False
    assert second_result["hotline_card"] is None


def test_graph_routes_voice_data_through_voice_analyzer(monkeypatch):
    """当 has_voice=True 时，voice_analyzer 应被触发。"""
    _set_emotion2vec_env(monkeypatch)
    graph = build_graph()
    result = asyncio.run(
        graph.ainvoke(
            _make_initial_state(
                "最近压力很大",
                has_voice=True,
                multimodal_features={
                    "voice_acoustic_features": {
                        "pause_count": 3,
                        "pause_total_ms": 1800,
                        "voiced_duration_ms": 1200,
                        "speech_ratio": 0.4,
                    }
                },
            ),
            config={"configurable": {"thread_id": "sess-voice-graph"}},
        )
    )
    assert result["reply"]
    # voice_analyzer 应该写入 agent_judgments
    assert "voice_analyzer" in result.get("agent_judgments", {})
    assert result["voice_signals"]["emotion2vec_reading"]["status"] == "disabled"


def test_graph_routes_face_data_through_face_analyzer():
    """当 has_face=True 时，face_analyzer 应被触发。"""
    graph = build_graph()
    result = asyncio.run(
        graph.ainvoke(
            _make_initial_state(
                "最近压力很大",
                has_face=True,
                multimodal_features={
                    "facial_data": {"emotion": "sad"},
                },
            ),
            config={"configurable": {"thread_id": "sess-face-graph"}},
        )
    )
    assert result["reply"]
    assert "face_analyzer" in result.get("agent_judgments", {})
