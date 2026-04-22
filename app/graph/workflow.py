"""LangGraph 工作流构建。

多智能体架构：
- fan-out：基于模态并行触发 text/voice/face analyzer
- fan-in：signal_aggregator 合并所有分析结果
- conditional edge：risk_router 决定是否走 referral_agent

图拓扑：
    START
      → modality_router (conditional fan-out)
        ├→ text_analyzer     (always)
        ├→ voice_analyzer    (if voice data)
        └→ face_analyzer     (if face data)
      → signal_aggregator    (fan-in)
      → rag_retriever
      → risk_assessor
      → risk_router (conditional edge)
        ├→ referral_agent → peer_support_retriever → response_generator → END
        └→ peer_support_retriever → response_generator → END
"""

from __future__ import annotations

from app.core.config import get_settings
from app.graph.routers import modality_router, risk_router
from app.graph.state import PsychologyGraphState
from app.nodes.face_analyzer import face_analyzer_node
from app.nodes.peer_support_retriever import peer_support_retriever_node
from app.nodes.rag_retriever import rag_retriever_node
from app.nodes.referral_agent import referral_agent_node
from app.nodes.response_generator import response_generator_node
from app.nodes.risk_assessor import risk_assessor_node
from app.nodes.signal_aggregator import signal_aggregator_node
from app.nodes.text_analyzer import text_analyzer_node
from app.nodes.voice_analyzer import voice_analyzer_node
from app.services.checkpoint_store import create_checkpointer
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """构建并编译风险识别流程图。"""

    graph_builder = StateGraph(PsychologyGraphState)

    # ── 注册所有 Agent 节点 ──
    graph_builder.add_node("text_analyzer", text_analyzer_node)
    graph_builder.add_node("voice_analyzer", voice_analyzer_node)
    graph_builder.add_node("face_analyzer", face_analyzer_node)
    graph_builder.add_node("signal_aggregator", signal_aggregator_node)
    graph_builder.add_node("rag_retriever", rag_retriever_node)
    graph_builder.add_node("risk_assessor", risk_assessor_node)
    graph_builder.add_node("referral_agent", referral_agent_node)
    graph_builder.add_node("peer_support_retriever", peer_support_retriever_node)
    graph_builder.add_node("response_generator", response_generator_node)

    # ── Fan-out：START → 模态路由 → 各 Analyzer ──
    graph_builder.add_conditional_edges(
        START,
        modality_router,
        ["text_analyzer", "voice_analyzer", "face_analyzer"],
    )

    # ── Fan-in：所有 Analyzer → signal_aggregator ──
    graph_builder.add_edge("text_analyzer", "signal_aggregator")
    graph_builder.add_edge("voice_analyzer", "signal_aggregator")
    graph_builder.add_edge("face_analyzer", "signal_aggregator")

    # ── 线性链：signal_aggregator → rag → risk ──
    graph_builder.add_edge("signal_aggregator", "rag_retriever")
    graph_builder.add_edge("rag_retriever", "risk_assessor")

    # ── 条件分支：risk_assessor → referral_agent 或 peer_support_retriever ──
    graph_builder.add_conditional_edges(
        "risk_assessor",
        risk_router,
        {
            "referral_agent": "referral_agent",
            "response_generator": "peer_support_retriever",
        },
    )

    # ── referral_agent 完成后也进入 peer_support_retriever ──
    graph_builder.add_edge("referral_agent", "peer_support_retriever")

    # ── peer_support_retriever → response_generator → END ──
    graph_builder.add_edge("peer_support_retriever", "response_generator")
    graph_builder.add_edge("response_generator", END)

    resolved_checkpointer = checkpointer or create_checkpointer(get_settings())
    return graph_builder.compile(checkpointer=resolved_checkpointer)


compiled_graph = build_graph()


def get_compiled_graph():
    """返回共享 graph 实例，确保不同路由使用同一 session memory。"""

    return compiled_graph
