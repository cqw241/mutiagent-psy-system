"""路由逻辑测试。"""

from app.graph.routers import modality_router, risk_router


def test_modality_router_always_includes_text():
    state = {"has_voice": False, "has_face": False}
    targets = modality_router(state)
    assert targets == ["text_analyzer"]


def test_modality_router_includes_voice_when_present():
    state = {"has_voice": True, "has_face": False}
    targets = modality_router(state)
    assert "text_analyzer" in targets
    assert "voice_analyzer" in targets
    assert "face_analyzer" not in targets


def test_modality_router_includes_face_when_present():
    state = {"has_voice": False, "has_face": True}
    targets = modality_router(state)
    assert "text_analyzer" in targets
    assert "face_analyzer" in targets
    assert "voice_analyzer" not in targets


def test_modality_router_includes_all_modalities():
    state = {"has_voice": True, "has_face": True}
    targets = modality_router(state)
    assert set(targets) == {"text_analyzer", "voice_analyzer", "face_analyzer"}


def test_risk_router_returns_referral_for_high():
    state = {"risk_level": "high"}
    assert risk_router(state) == "referral_agent"


def test_risk_router_returns_response_for_medium():
    state = {"risk_level": "medium"}
    assert risk_router(state) == "response_generator"


def test_risk_router_returns_response_for_low():
    state = {"risk_level": "low"}
    assert risk_router(state) == "response_generator"


def test_risk_router_returns_response_for_missing_risk():
    state = {}
    assert risk_router(state) == "response_generator"
