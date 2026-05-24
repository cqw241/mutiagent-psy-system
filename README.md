# 面向高校学生心理风险早期识别与转介辅助的多智能体协同系统

这是一个面向高校场景的心理风险早期识别、支持性回应与规范转介辅助系统。它基于 FastAPI、LangGraph、RAGFlow 和 React 构建，把学生的文本、语音和端侧面部辅助观察拆解为多个 Agent 并行处理，再汇聚成风险分级、转介告警、可解释 trace 和温和回复。

系统定位是“试点前工程原型”：可联调、可演示、可回归验证，也已经具备高风险告警事件、WebSocket 风险事件契约和风险评测 harness。但它不替代心理咨询师，不输出医学诊断，不提供治疗方案。

最新技术白皮书见 [TECHNICAL_WHITEPAPER.md](TECHNICAL_WHITEPAPER.md)。短期开发节奏见 [docs/plans/短期1-2周开发计划.md](docs/plans/短期1-2周开发计划.md)，中长期诊断与路线图见 [docs/plans/2026-05-22-project-diagnosis-and-development-plan.md](docs/plans/2026-05-22-project-diagnosis-and-development-plan.md)。

## 当前状态

截至 2026-05-25，短期 1-2 周工程闭环已完成到 PR #4，且 GitHub Actions checks 已通过；前 4 个阶段已合入 `main`，CI 收尾分支待合入：

- `feature/short-term-doc-baseline`：校准 README、白皮书、环境变量和短期路线图。
- `feature/alert-event-store-v0`：新增高风险告警事件模型与 file-backed JSONL store。
- `feature/ws-risk-event-contract`：稳定 WebSocket `final` 与 `risk_event` 风险事件契约。
- `feature/risk-eval-harness-v0`：新增 34 条 seed case 风险评测集、离线评测脚本，并修补高危漏报和误报规则。
- `feature/ci-smoke-checks`：新增 GitHub Actions smoke、本地 `scripts/ci_check.sh`、前端 `test:node` 脚本，并修复 CI runner 缺少 PortAudio 时 ASR 可选依赖导入失败的问题。

当前尚未完成生产级 PostgreSQL/Redis checkpoint、正式管理员后台、多角色权限、真实校内 SOP 和容器化部署。这些仍在后续计划中。

## 核心能力

### 多智能体工作流

后端使用 LangGraph 组织 9 个核心节点：

- `text_analyzer`：提取文本情绪关键词、风险线索和简要观察。
- `voice_analyzer`：处理声学特征、MFCC、启发式语音情绪线索和可选 emotion2vec 结果。
- `face_analyzer`：消费前端端侧 MediaPipe FACS/AU 结构化特征，不接收原始视频。
- `signal_aggregator`：汇总文本、语音、面部观察为统一 `extracted_signals`。
- `rag_retriever`：从 RAGFlow 相似案例库检索风险参考上下文。
- `risk_assessor`：结合规则、LLM JSON、RAG 上下文和声学轻度校准输出 `low` / `medium` / `high`。
- `referral_agent`：仅高风险触发，生成温和转介过渡语、热线卡片和告警事件。
- `peer_support_retriever`：检索同辈倾听话术样例，辅助最终回复风格。
- `response_generator`：生成最终支持性回复，并可流式输出 token / TTS 事件。

```mermaid
flowchart LR
    Start([START]) --> Router{modality_router}
    Router --> Text[text_analyzer]
    Router --> Voice[voice_analyzer]
    Router --> Face[face_analyzer]
    Text --> Aggregate[signal_aggregator]
    Voice --> Aggregate
    Face --> Aggregate
    Aggregate --> RAG[rag_retriever]
    RAG --> Risk[risk_assessor]
    Risk --> Decision{risk_router}
    Decision -->|high| Referral[referral_agent]
    Decision -->|low / medium| Peer[peer_support_retriever]
    Referral --> Peer
    Peer --> Response[response_generator]
    Response --> End([END])
```

更完整的架构图见 [docs/diagrams/core-architecture-mermaid.md](docs/diagrams/core-architecture-mermaid.md)。

### 高风险告警闭环 v0

高风险会话会先写入本地告警事件，再尝试投递辅导员 webhook。事件模型位于 `app/models/schemas.py`，文件存储实现位于 `app/services/alert_event_store.py`。

当前事件字段包括：

- `alert_event_id`
- `trigger_time`
- `updated_at`
- `masked_session_id`
- `risk_level`
- `latest_risk_evidence`
- `delivery_status`
- `ack_status`
- `handler_status`
- `trace_id`
- `summary`

默认存储路径是 `.alert-events/alert-events.jsonl`。Webhook 失败不会丢事件，会将 `delivery_status` 标为 `delivery_failed`。当前这是单机试点前版本，不等同正式告警工单系统。

### WebSocket 风险事件契约

文本和语音 WebSocket 都会在最终事件中返回稳定风险字段：

```json
{
  "type": "final",
  "reply": "...",
  "risk_level": "low",
  "referral_required": false,
  "alert_status": {},
  "alert_event_id": null,
  "trace_id": "...",
  "trace": {}
}
```

高风险时会在 `final` 前额外发送 `risk_event`：

```json
{
  "type": "risk_event",
  "alert_event_id": "alert_xxx",
  "risk_level": "high",
  "handler_status": "created",
  "delivery_status": "delivered",
  "trace_id": "...",
  "masked_session_id": "session-xxxxxxxxxx",
  "summary": "检测到需要人工关注的高风险心理支持对话，请尽快复核。"
}
```

前端当前只把 `risk_event` 合并到 trace/状态辅助信息，不改变消息渲染和 TTS 流。

### 风险评测 harness

仓库内置风险工程基线评测：

- Casebook：`evals/risk_cases/risk_casebook_seed_v1.jsonl`
- 脚本：`scripts/run_risk_eval.py`
- 测试：`tests/test_risk_eval_cases.py`

当前 seed case 共 34 条，覆盖高危明确表达、方法/准备行为、失眠与功能受损、普通学业压力、歌词引用、转述朋友风险、否定自伤、新闻讨论和夸张吐槽等边界样本。

运行：

```bash
conda run -n llm_env python scripts/run_risk_eval.py \
  --mode node \
  --output-json /tmp/risk_eval_node.json \
  --output-md /tmp/risk_eval_node.md
```

评测输出是工程回归 baseline，不是临床标签或专家审定结论。当前 node 模式可达到高危召回 `1.000`，且 34 条 seed case 中高危 false positive / false negative 为空；剩余误差集中在非高危 low/medium 边界。

### 多模态与隐私边界

- 文本：LLM 与规则共同参与，但高风险规则兜底不能被 LLM 单独覆盖。
- 语音：支持 ASR、F0/RMS/silence ratio/MFCC、启发式观察和可选 emotion2vec。语音信号只能辅助低/中风险校准，不能单独触发高危。
- 面部：前端使用 MediaPipe 本地提取 AU/FACS 与复合情绪得分，只上传结构化特征，不上传原始视频。
- RAG：风险案例检索和同辈倾听话术检索可分别开关，RAGFlow 不可用时降级为空上下文。

## 目录结构

```text
app/
  api/routes/              # REST 与 WebSocket 路由
  core/config.py           # 环境变量与设置校验
  graph/                   # LangGraph state、routers、workflow
  models/                  # Pydantic 接口与事件模型
  nodes/                   # 多智能体节点
  prompts/                 # 集中管理的系统提示词与 prompt builders
  rag/                     # RAGFlow 客户端与检索逻辑
  services/                # LLM、ASR、TTS、告警、checkpoint、trace、音频特征等服务
  utils/                   # 状态构建与合并工具
docs/
  diagrams/                # 架构图
  plans/                   # 开发计划与诊断路线图
  rag/                     # RAGFlow、本地 embedding 与知识库联调文档
  whitepapers/             # 历史白皮书入口说明
evals/
  risk_cases/              # 风险评测 casebook
frontend/
  src/                     # React 前端
scripts/
  run_risk_eval.py         # 风险评测脚本
tests/                     # 后端 pytest
```

## 环境准备

推荐使用 Conda `llm_env` 或其他明确隔离的 Python 环境。不要把项目依赖安装到系统 Python。

```bash
conda create -n llm_env python=3.11
conda activate llm_env
python -m pip install -r requirements.txt
```

复制环境变量模板：

```bash
cp .env.example .env
```

关键配置：

- `LLM_PROVIDER`、`LLM_MODEL`、`LLM_API_KEY`、`LLM_BASE_URL`
- `TTS_ENABLED`、`TTS_PROVIDER`、`TTS_API_KEY`、`TTS_MODEL`
- `COUNSELOR_ALERT_WEBHOOK`
- `ENABLE_RAG`、`RAGFLOW_BASE_URL`、`RAGFLOW_API_KEY`、`RAGFLOW_DATASET_ID`
- `ENABLE_PEER_SUPPORT_RAG`、`RAGFLOW_PEER_SUPPORT_DATASET_ID`
- `CHECKPOINT_BACKEND`、`CHECKPOINT_DIR`
- `ENABLE_EMOTION2VEC`、`EMOTION2VEC_MODEL_DIR`

`CHECKPOINT_BACKEND=memory` 适合开发测试；`file` 适合单机试点前验证。`postgres` 和 `redis` 目前是配置契约预留，仓库尚未内置生产级 saver 依赖与迁移。

`COUNSELOR_ALERT_WEBHOOK=mock://counselor-alert` 或本地 mock 地址只能验证投递调用，不代表真实校内告警闭环。

## 启动

后端：

```bash
conda activate llm_env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

前端使用 `pnpm`：

```bash
cd frontend
pnpm install
pnpm run dev -- --host 0.0.0.0
```

访问 `http://localhost:5173`。

如果要启用视频通话中的端侧面部分析，请确认 `frontend/public/models/face_landmarker.task` 存在。

## 接口速查

REST：

- `POST /chat`

WebSocket：

- `WS /ws/chat/{session_id}`
- `WS /ws/voice-chat/{session_id}`

REST `/chat` 返回结构化 `reply`、`risk_level`、`referral_required`、`trace_id`、`trace`、`hotline_card` 和 `alert_status`。WebSocket 返回 `stage`、`token`、可选 `tts_audio` / `tts_end`、高风险 `risk_event`、最终 `final` 和 `end`。

## RAG 与本地 embedding

RAGFlow 启动和本地 BGE-M3 联调见 [docs/rag/start_command.md](docs/rag/start_command.md)。

如需启动 OpenAI-compatible BGE-M3 embedding 服务：

```bash
python scripts/bge_m3_embedding_server.py \
  --model-path /path/to/bge-m3 \
  --host 0.0.0.0 \
  --port 8001
```

健康检查：

```bash
curl -s http://127.0.0.1:8001/health
```

## 测试与验证

后端全量测试：

```bash
conda run -n llm_env python -m pytest -q --tb=short
```

风险评测：

```bash
conda run -n llm_env python scripts/run_risk_eval.py --mode mock
conda run -n llm_env python scripts/run_risk_eval.py --mode node
```

前端构建与 lint：

```bash
pnpm --dir frontend run build
pnpm --dir frontend run lint
```

前端逻辑测试当前使用 Node 内置 test runner：

```bash
pnpm --dir frontend run test:node
```

本地同款 smoke 入口：

```bash
PYTHON_BIN=/path/to/env/python bash scripts/ci_check.sh
```

CI 入口位于 `.github/workflows/ci.yml`，覆盖后端 pytest、risk eval mock、前端 node tests、lint 和 build。GitHub runner 会安装 `libportaudio2`，避免 `sounddevice` 在缺少 PortAudio 时影响后端测试收集。

## 数据保存与安全边界

当前默认原则：

- 允许保存完整对话文本和 ASR 转写，用于审计、复盘和试点问题定位。
- 默认不保存原始视频。
- 原始音频默认不长期保存，仅保留转写、声学特征、必要 trace 和事件摘要。
- 高风险事件使用 `masked_session_id` 对外投递，避免把原始会话 ID 暴露给 webhook。
- 风险评测标签仅为工程 baseline，不能宣传为专业临床标注。

正式校内试点前仍需要由学校心理中心、伦理、法务和信息安全团队确认保留期限、访问权限、删除流程和真实 SOP。

## 近期计划

短期 1-2 周计划已完成，详见 [docs/plans/短期1-2周开发计划.md](docs/plans/短期1-2周开发计划.md)。后续重点：

1. 最小管理员后台：告警列表、事件详情、接单、升级、结案、回执。
2. 真实校内 SOP 与资源接入：替换当前热线占位和 mock webhook。
3. 数据治理与审计：生产级 checkpoint、审计存储、导出/删除路径。
4. 容器化和部署硬化：docker-compose、生产环境变量、健康检查和回滚流程。

中长期方向包括本地大模型路由、多实例持久化、多模态时序建模、专家复核样本集和校园运营看板。
