"""RAGFlow 异步客户端。"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RagFlowClient:
    """封装对 RAGFlow 检索接口的访问。"""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        dataset_id: str | None = None,
        timeout_seconds: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ragflow_base_url).rstrip("/")
        self.api_key = api_key or settings.ragflow_api_key
        self.dataset_id = dataset_id or settings.ragflow_dataset_id
        self.timeout_seconds = timeout_seconds or settings.ragflow_timeout_seconds
        self.transport = transport
        # 基于 RAGFlow 官方仓库中的 dify-compatible retrieval 实现做兼容。
        self.candidate_paths = ("/api/v1/dify/retrieval", "/dify/retrieval")

    async def retrieve_similar_cases(self, query: str, top_k: int = 3) -> str:
        """检索相似案例，失败时优雅降级为空字符串。"""

        if (
            not query.strip()
            or not self.api_key
            or not self.dataset_id
            or (os.getenv("PYTEST_CURRENT_TEST") and self.transport is None)
        ):
            return ""

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "knowledge_id": self.dataset_id,
            "query": query,
            "metadata_condition": None,
            "retrieval_setting": {
                "top_k": top_k,
                "score_threshold": 0.0,
            },
        }

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            for path in self.candidate_paths:
                try:
                    response = await client.post(
                        f"{self.base_url}{path}",
                        headers=headers,
                        json=payload,
                    )
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                    return self._extract_context(response.json(), top_k=top_k)
                except httpx.TimeoutException:
                    logger.warning(
                        "RAGFlow unavailable, skipping retrieval due to timeout query=%s",
                        query,
                    )
                    return ""
                except httpx.ConnectError as exc:
                    logger.warning(
                        "RAGFlow unavailable, skipping retrieval due to connection error path=%s error=%s",
                        path,
                        exc,
                    )
                    return ""
                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code
                    if status_code in {502, 503, 504}:
                        logger.warning(
                            "RAGFlow unavailable, skipping retrieval due to upstream status=%s path=%s",
                            status_code,
                            path,
                        )
                    else:
                        logger.warning(
                            "RAGFlow retrieval failed with status=%s path=%s",
                            status_code,
                            path,
                        )
                    return ""
                except Exception as exc:
                    logger.warning(
                        "RAGFlow unavailable, skipping retrieval due to unexpected error path=%s error=%s",
                        path,
                        exc,
                    )
                    return ""

        logger.warning("No valid RAGFlow retrieval endpoint found under %s", self.base_url)
        return ""

    @staticmethod
    def _extract_context(payload: dict[str, Any], top_k: int) -> str:
        """兼容不同返回结构，提取内容片段。"""

        records = payload.get("records")
        if isinstance(records, list):
            snippets = [
                item.get("content", "").strip()
                for item in records[:top_k]
                if isinstance(item, dict) and item.get("content")
            ]
            return "\n\n".join(snippets)

        data = payload.get("data")
        if isinstance(data, dict):
            chunks = data.get("chunks")
            if isinstance(chunks, dict):
                snippets = [
                    item.get("content", "").strip()
                    for item in list(chunks.values())[:top_k]
                    if isinstance(item, dict) and item.get("content")
                ]
                return "\n\n".join(snippets)

        return ""
