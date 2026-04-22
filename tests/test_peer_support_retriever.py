"""peer_support_retriever 节点单元测试。"""

import asyncio

from app.nodes import peer_support_retriever
from app.nodes.peer_support_retriever import peer_support_retriever_node


class DummyPeerSupportClient:
    async def retrieve_similar_cases(self, query: str, top_k: int = 2) -> str:
        return (
            "听起来你现在的确被考试压得喘不过气了。"
            "复习不完真的会让人觉得特别绝望和挫败。"
        )


class FailingPeerSupportClient:
    async def retrieve_similar_cases(self, query: str, top_k: int = 2) -> str:
        raise RuntimeError("ragflow offline")


class ShouldNotBeCalledClient:
    async def retrieve_similar_cases(self, query: str, top_k: int = 2) -> str:
        raise AssertionError("Client should be bypassed when disabled")


def _make_state(text: str = "我好焦虑") -> dict:
    return {
        "session_id": "test-sess",
        "chat_history": [{"role": "user", "content": text}],
        "multimodal_features": {},
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {},
        "reference_context": "",
        "peer_support_context": "",
        "risk_level": "low",
        "referral_required": False,
    }


def test_peer_support_retriever_writes_context_when_enabled(monkeypatch):
    """开关启用 + 检索成功：peer_support_context 非空。"""

    class EnabledSettings:
        enable_peer_support_rag = True
        ragflow_peer_support_dataset_id = "dataset-peer"

    monkeypatch.setattr(peer_support_retriever, "get_settings", lambda: EnabledSettings())

    state = _make_state()
    updated = asyncio.run(
        peer_support_retriever_node(state, rag_client=DummyPeerSupportClient())
    )

    assert updated["peer_support_context"] != ""
    assert "考试" in updated["peer_support_context"]
    assert updated["agent_judgments"]["peer_support_retriever"]["reference_found"] is True
    assert updated["agent_judgments"]["peer_support_retriever"]["enabled"] is True


def test_peer_support_retriever_returns_empty_when_disabled(monkeypatch):
    """开关禁用：不调用客户端，返回空。"""

    class DisabledSettings:
        enable_peer_support_rag = False
        ragflow_peer_support_dataset_id = ""

    monkeypatch.setattr(peer_support_retriever, "get_settings", lambda: DisabledSettings())

    state = _make_state()
    updated = asyncio.run(
        peer_support_retriever_node(state, rag_client=ShouldNotBeCalledClient())
    )

    assert updated["peer_support_context"] == ""
    assert updated["agent_judgments"]["peer_support_retriever"]["enabled"] is False


def test_peer_support_retriever_degrades_on_exception(monkeypatch):
    """检索异常：降级为空字符串，不抛异常。"""

    class EnabledSettings:
        enable_peer_support_rag = True
        ragflow_peer_support_dataset_id = "dataset-peer"

    monkeypatch.setattr(peer_support_retriever, "get_settings", lambda: EnabledSettings())

    state = _make_state()
    updated = asyncio.run(
        peer_support_retriever_node(state, rag_client=FailingPeerSupportClient())
    )

    assert updated["peer_support_context"] == ""
    assert updated["agent_judgments"]["peer_support_retriever"]["reference_found"] is False
