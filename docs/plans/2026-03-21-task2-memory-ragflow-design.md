# Task 2 Memory And RAGFlow Design

## Goal

在 Task 1 的多智能体后端骨架上，加入 session 级别的多轮会话记忆，并通过独立的检索节点接入外部 RAGFlow 引擎，为风险评估提供专业参考上下文。

## Chosen Architecture

采用 `LangGraph + MemorySaver + 独立 rag_retriever_node` 的四节点图：

`START -> information_extractor -> rag_retriever -> risk_assessor -> response_generator -> END`

关键原则：

- 会话记忆由 LangGraph checkpointer 负责，而不是前端重复传历史。
- 检索职责与评估职责分离，保证图结构可解释、节点单一职责明确。
- 风险评估继续保留“RAG 参考 + LLM 判断 + 规则兜底”的三层结构，避免把风控完全交给模型。

## State Changes

在 `PsychologyGraphState` 中新增：

- `reference_context`：RAGFlow 检索回来的相似案例或专业标准文本

并为 `chat_history` 添加 reducer，使每轮请求仅追加当前用户消息和当前助手回复，而不是覆盖旧历史。

## Graph Runtime

- `build_graph()` 使用 `MemorySaver` 编译图
- `/chat` 调用 graph 时使用：
  `config={"configurable": {"thread_id": session_id}}`
- 路由不再伪造整段历史，只提交本轮增量消息

## RAGFlow Integration

新增 `app/rag/ragflow_client.py`，用 `httpx.AsyncClient` 调用 RAGFlow 检索接口。

实现策略：

- 从配置读取 `RAGFLOW_BASE_URL`、`RAGFLOW_API_KEY`、`RAGFLOW_DATASET_ID`
- 请求头使用 `Authorization: Bearer <API_KEY>`
- 请求失败、超时、返回脏数据时统一降级为空字符串并记录日志

这里优先采用 RAGFlow 官方仓库中的 Dify-compatible retrieval 端点实现思路，将本地 `dataset_id` 作为 `knowledge_id` 传入。若后续你确认部署版本的检索 API 路径不同，只需调整客户端，不影响图节点。

## Testing Strategy

测试分三层：

1. `ragflow_client` 单元测试：用 `httpx.MockTransport` 或打桩 `AsyncClient.post` 模拟成功、超时、异常响应
2. `workflow` / `chat` 测试：验证相同 `session_id` 的多轮调用能保留历史
3. `risk_assessor` 测试：验证会消费 `reference_context`，且 RAG 空返回时仍能正常降级
