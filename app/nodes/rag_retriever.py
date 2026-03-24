"""独立的 RAG 检索节点。"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.rag.ragflow_client import RagFlowClient

logger = logging.getLogger(__name__)


def _latest_user_message(state: dict[str, Any]) -> str:
    for message in reversed(state.get("chat_history", [])):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


async def rag_retriever_node(
    state: dict[str, Any], rag_client: RagFlowClient | None = None
) -> dict[str, Any]:
    """把检索到的参考案例写入全局状态。"""

    latest_text = _latest_user_message(state)
    settings = get_settings()

    if not settings.enable_rag:
        agent_judgments = dict(state.get("agent_judgments", {}))
        agent_judgments["rag_retriever"] = {
            "query": latest_text,
            "reference_found": False,
            "enabled": False,
        }
        return {
            "reference_context": "",
            "agent_judgments": agent_judgments,
        }

    client = rag_client or RagFlowClient()
    try:
        reference_context = await client.retrieve_similar_cases(latest_text, top_k=3)
    except Exception as exc:
        logger.warning("RAGFlow unavailable, skipping retrieval at node level: %s", exc)
        reference_context = ""

    agent_judgments = dict(state.get("agent_judgments", {}))
    agent_judgments["rag_retriever"] = {
        "query": latest_text,
        "reference_found": bool(reference_context),
        "enabled": True,
    }

    return {
        "reference_context": reference_context,
        "agent_judgments": agent_judgments,
    }
