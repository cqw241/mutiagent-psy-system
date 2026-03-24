import asyncio

from app.nodes import rag_retriever
from app.nodes.rag_retriever import rag_retriever_node


class DummyRagFlowClient:
    async def retrieve_similar_cases(self, query: str, top_k: int = 3) -> str:
        assert query == "最近总是睡不着"
        return "案例A：连续失眠时应提高风险关注。"


class FailingRagFlowClient:
    async def retrieve_similar_cases(self, query: str, top_k: int = 3) -> str:
        raise RuntimeError("ragflow offline")


class ShouldNotBeCalledRagFlowClient:
    async def retrieve_similar_cases(self, query: str, top_k: int = 3) -> str:
        raise AssertionError("RAG client should be bypassed when ENABLE_RAG is false")


def test_rag_retriever_node_writes_reference_context(monkeypatch):
    class EnabledSettings:
        enable_rag = True

    monkeypatch.setattr(rag_retriever, "get_settings", lambda: EnabledSettings())

    state = {
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "最近总是睡不着"}],
        "multimodal_features": {},
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {},
        "reference_context": "",
        "risk_level": "low",
        "referral_required": False,
    }
    updated = asyncio.run(rag_retriever_node(state, rag_client=DummyRagFlowClient()))
    assert "案例A" in updated["reference_context"]


def test_rag_retriever_node_returns_empty_context_when_rag_client_fails():
    state = {
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "最近总是睡不着"}],
        "multimodal_features": {},
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {},
        "reference_context": "",
        "risk_level": "low",
        "referral_required": False,
    }

    updated = asyncio.run(rag_retriever_node(state, rag_client=FailingRagFlowClient()))

    assert updated["reference_context"] == ""
    assert updated["agent_judgments"]["rag_retriever"]["reference_found"] is False


def test_rag_retriever_node_bypasses_retrieval_when_rag_disabled(monkeypatch):
    class DisabledSettings:
        enable_rag = False

    monkeypatch.setattr(rag_retriever, "get_settings", lambda: DisabledSettings())

    state = {
        "session_id": "sess-1",
        "chat_history": [{"role": "user", "content": "最近总是睡不着"}],
        "multimodal_features": {},
        "current_risk_score": 0.0,
        "agent_judgments": {},
        "extracted_signals": {},
        "reference_context": "",
        "risk_level": "low",
        "referral_required": False,
    }

    updated = asyncio.run(
        rag_retriever_node(state, rag_client=ShouldNotBeCalledRagFlowClient())
    )

    assert updated["reference_context"] == ""
    assert updated["agent_judgments"]["rag_retriever"]["reference_found"] is False
