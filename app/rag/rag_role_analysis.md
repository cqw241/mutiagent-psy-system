# 项目 RAG 架构与 RAGFlow 作用详细解析

在目前的多智能体心理风险系统中，RAG (Retrieval-Augmented Generation，检索增强生成) 主要用于给大模型补充**专业的心理评估标准**或**历史相似案例**，从而让 AI 的风险判定基于严肃依据，而非天马行空的幻觉。

其中，**RAGFlow** 是作为一个外置的高性能知识库服务端，为我们的 LangGraph 节点提供检索接口。

目前项目的 RAG 机制具体在以下几个环节流转运作：

## 1. [rag_retriever](file:///home/chai/mutiagent-psy-system/app/nodes/rag_retriever.py#21-59) 节点的拦截与索检
所有的用户互动文本，在经过情绪分析等初期节点后，如果全局设定开启了 RAG (`settings.enable_rag` 为 True)，就会流入系统图(Graph)中的独立节点：[app/nodes/rag_retriever.py](file:///home/chai/mutiagent-psy-system/app/nodes/rag_retriever.py)。
- **提取 Query：** 该节点会提取用户最近一轮的对话内容。
- **发起请求：** 节点调用我们封装的 [RagFlowClient](file:///home/chai/mutiagent-psy-system/app/rag/ragflow_client.py#16-140)，异步将该对话发送给外部署的 RAGFlow 服务。
- **状态注入：** 获取到的最相关的 Top-K (当前设为前3个) 案例或标准文本，会被写进系统的全局状态变量 `reference_context` 中。

## 2. `ragflow_client` 的安全兜底设计
在 [app/rag/ragflow_client.py](file:///home/chai/mutiagent-psy-system/app/rag/ragflow_client.py) 中，你可以看到对 RAGFlow 服务调用的具体封装。这个项目的特色在于极其重视系统的**鲁棒性和优雅降级**：
- **兼容性：** 由于系统采用 RAGFlow，为了请求标准化，代码中兼容了基于 Dify 格式的查询接口（例如 `/api/v1/dify/retrieval`）。
- **非阻塞与容错：** 使用 `httpx.AsyncClient` 进行并发安全的异步网络请求；如果在校园网环境断网、服务端 502/504 甚至超时 (`TimeoutException`)，该客户端不会让整个路由崩溃，而是立刻捕获异常，并且返回空字符串 `""`。这种机制确保了在无法连接知识库服务时，系统能立即切为“无源模式”继续运行，让后续风险评估平滑过渡。

## 3. RAGFlow 如何影响最终决策 (`risk_assessor` 节点)
这是 RAG 发挥作用的最核心环节。我们在 [app/prompts/system_prompts.py](file:///home/chai/mutiagent-psy-system/app/prompts/system_prompts.py) 里的 `RISK_ASSESSOR_SYSTEM_PROMPT_TEMPLATE`（负责打分的风险评估节点 Prompt）看到了如下的严格规定：
```text
<Reference_Cases>
{reference_context}
</Reference_Cases>
"请结合这些检索到的历史相似案例和心理评估标准，对当前用户的状况进行风险打分。"
"如果有矛盾，优先参考 RAG 提供的专业标准。"
```
- **注入模板：** [rag_retriever](file:///home/chai/mutiagent-psy-system/app/nodes/rag_retriever.py#21-59) 取到的 `reference_context` 在这里被直接铺进了风控大模型的 Prompt 里。
- **一票否决权（最高优先级）：** LLM 被明确指示：如果它自身的内部常识判断与 RAG 提供的内容发生了对立，必须**优先参考 RAG 提供的专业标准**。

## 总结：RAGFlow 在本项目的定位

1. **作为权威的心理知识库后端：** RAGFlow 不参与系统的业务路由决策，而是作为一本“动态词典/案例库”，里面很可能存储了《高校真实危机干预案例库》或《安全干预标准手册》。
2. **作为大模型定风控等级的锚点：** 它拉住了大模型，防止大模型仅由于语气激动就给普通的“考试抱怨”打出“High Risk”——如果有对应的低危案例对照在那，大模型就会“照章办事”。
3. **架构松耦合：** RAGFlow 与 FastAPI / LangGraph 完全解耦，这代表如果未来需要换成其他的知识检索服务端（比如直连 Elasticsearch 或 Milvus），或者它宕机断联，项目主业务依旧能顺畅进行，不引发连锁崩溃。
