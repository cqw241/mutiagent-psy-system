from app.graph.state import PsychologyGraphState
from app.models.schemas import ChatRequest, ChatResponse


def test_chat_request_supports_engineering_payload():
    payload = ChatRequest(
        session_id="sess-1",
        message="我最近很累",
        multimodal_features={"facial_emotion": "sad"},
        user_profile={"grade": "freshman"},
    )
    assert payload.session_id == "sess-1"
    assert payload.multimodal_features["facial_emotion"] == "sad"


def test_state_type_contains_required_keys():
    required = PsychologyGraphState.__annotations__
    assert "chat_history" in required
    assert "multimodal_features" in required
    assert "voice_segments" in required
    assert "trace" in required
    assert "current_risk_score" in required
    assert "agent_judgments" in required
    assert "reference_context" in required


def test_chat_response_supports_optional_trace_payload():
    payload = ChatResponse(
        reply="我在这里",
        risk_level="low",
        referral_required=False,
        trace_id="trace-1",
        trace={
            "latest_voice_segment": None,
            "acoustic_observations": [],
            "acoustic_support_level": "none",
            "risk_calibration": {
                "base_score": 0.2,
                "adjusted_score": 0.2,
                "risk_level": "low",
                "used_acoustic_adjustment": False,
            },
        },
    )
    assert payload.trace["acoustic_support_level"] == "none"
