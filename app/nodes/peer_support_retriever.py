"""同辈倾听话术检索节点。

职责：
从 Peer Support 知识库中检索与用户当前表达最相似的同辈倾听话术样例，
写入 ``peer_support_context``，供 ``response_generator`` 做风格对齐参照。

设计要点：
- 复用已有 ``RagFlowClient``，仅通过 ``dataset_id`` 参数指向不同知识库。
- 独立开关 ``ENABLE_PEER_SUPPORT_RAG``，与风险案例库检索完全解耦。
- 失败或关闭时静默降级为空字符串，不影响主链路。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.rag.ragflow_client import RagFlowClient
from app.utils.state_helpers import latest_user_message, merge_agent_judgment

logger = logging.getLogger(__name__)


async def peer_support_retriever_node(
    state: dict[str, Any],
    rag_client: RagFlowClient | None = None,
) -> dict[str, Any]:
    """检索同辈倾听话术样例并写入图状态。"""

    latest_text = latest_user_message(state)
    settings = get_settings()

    if not settings.enable_peer_support_rag:
        return {
            "peer_support_context": "",
            "agent_judgments": merge_agent_judgment(
                state,
                "peer_support_retriever",
                {"query": latest_text, "reference_found": False, "enabled": False},
            ),
        }

    client = rag_client or RagFlowClient(
        dataset_id=settings.ragflow_peer_support_dataset_id,
    )

    try:
        peer_support_context = await client.retrieve_similar_cases(latest_text, top_k=2)
    except Exception as exc:
        logger.warning(
            "Peer support RAG unavailable, skipping retrieval: %s", exc
        )
        peer_support_context = ""

    return {
        "peer_support_context": peer_support_context,
        "agent_judgments": merge_agent_judgment(
            state,
            "peer_support_retriever",
            {
                "query": latest_text,
                "reference_found": bool(peer_support_context),
                "enabled": True,
            },
        ),
    }
