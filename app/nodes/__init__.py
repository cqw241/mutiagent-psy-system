"""Agent 节点注册。"""

from app.nodes.face_analyzer import face_analyzer_node
from app.nodes.rag_retriever import rag_retriever_node
from app.nodes.referral_agent import referral_agent_node
from app.nodes.response_generator import response_generator_node
from app.nodes.risk_assessor import risk_assessor_node
from app.nodes.signal_aggregator import signal_aggregator_node
from app.nodes.text_analyzer import text_analyzer_node
from app.nodes.voice_analyzer import voice_analyzer_node

__all__ = [
    "text_analyzer_node",
    "voice_analyzer_node",
    "face_analyzer_node",
    "signal_aggregator_node",
    "rag_retriever_node",
    "risk_assessor_node",
    "referral_agent_node",
    "response_generator_node",
]
