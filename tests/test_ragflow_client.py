import asyncio
import json

import httpx

from app.rag.ragflow_client import RagFlowClient


def test_retrieve_similar_cases_returns_joined_content():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"].startswith("Bearer ")
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["knowledge_id"]
        assert payload["query"] == "用户最近持续失眠"
        return httpx.Response(
            200,
            json={
                "records": [
                    {"content": "案例一：持续失眠伴随绝望表达。"},
                    {"content": "案例二：出现退缩和学业功能下降。"},
                ]
            },
        )

    client = RagFlowClient(
        base_url="http://127.0.0.1",
        api_key="ragflow-demo-key",
        dataset_id="dataset-demo",
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(client.retrieve_similar_cases("用户最近持续失眠", top_k=2))
    assert "案例一" in result
    assert "案例二" in result


def test_retrieve_similar_cases_returns_empty_string_on_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    client = RagFlowClient(
        base_url="http://127.0.0.1",
        api_key="ragflow-demo-key",
        dataset_id="dataset-demo",
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(client.retrieve_similar_cases("用户最近持续失眠"))
    assert result == ""


def test_retrieve_similar_cases_returns_empty_string_on_502(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"message": "bad gateway"})

    client = RagFlowClient(
        base_url="http://127.0.0.1",
        api_key="ragflow-demo-key",
        dataset_id="dataset-demo",
        transport=httpx.MockTransport(handler),
    )

    with caplog.at_level("WARNING"):
        result = asyncio.run(client.retrieve_similar_cases("用户最近持续失眠"))

    assert result == ""
    assert "RAGFlow unavailable, skipping retrieval" in caplog.text


def test_retrieve_similar_cases_returns_empty_string_on_connection_error(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = RagFlowClient(
        base_url="http://127.0.0.1",
        api_key="ragflow-demo-key",
        dataset_id="dataset-demo",
        transport=httpx.MockTransport(handler),
    )

    with caplog.at_level("WARNING"):
        result = asyncio.run(client.retrieve_similar_cases("用户最近持续失眠"))

    assert result == ""
    assert "RAGFlow unavailable, skipping retrieval" in caplog.text
