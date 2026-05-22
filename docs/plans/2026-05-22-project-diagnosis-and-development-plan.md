# 项目诊断与后续开发计划

日期：2026-05-22  
对象：面向高校学生心理风险早期识别与转介辅助的多智能体协同系统  
依据：`README.md`、`docs/whitepapers/2026-04-2-project-introduction-whitepaper.md`、当前代码结构与测试资产

2026-05-22 追加决策：

- `docs/plans` 早期历史计划文件已作为冗余文件有意清理，当前计划为后续研发决策基线。
- 真实校内 SOP 尚未确定，先由本计划给出默认最小 SOP。
- 允许保存完整对话文本；数据保留、权限和最小化策略按本计划默认方案执行。
- 第一版产品角色收敛为“学生端 + 单一管理员”。
- 风险评测方案采用工程 baseline + 专业抽检的两层机制。
- 本地大模型是 3-6 个月能力扩展，不作为 1-2 周或 1-2 个月阶段阻塞项。
- WebSocket 对外协议采用稳定 `final` / `risk_event` 方案。

## 1. 项目当前状态概览

本项目当前是一套面向高校心理风险早期识别与规范转介的多智能体工程原型。它不是普通心理聊天机器人，核心假设是：学生的文本、语音与端侧面部辅助观察可以被拆解为多个独立 Agent 的结构化信号，再通过 LangGraph Fan-out/Fan-in 图拓扑汇聚，结合相似案例 RAG、规则兜底与 LLM 判断完成风险分级，并在高风险时强制进入转介与告警链路。

当前阶段应定义为“试点前版本 / 可联调验证版本 / 可继续硬化的工程原型”。README 明确写到当前建议视为“可联调、可验证、可继续硬化的试点前版本”，进入校内试点前要优先完成持久化、审计和 CI 基建（`README.md:3-5`）。白皮书也给出同样判断：项目已经超过概念验证，但尚未达到校内生产稳定运行阶段（`docs/whitepapers/2026-04-2-project-introduction-whitepaper.md:414-424`）。

已完成的核心能力包括：

- 多 Agent 图编排：`app/graph/workflow.py` 注册 9 个节点，并从 START 条件 fan-out 到 `text_analyzer`、`voice_analyzer`、`face_analyzer`，再 fan-in 到 `signal_aggregator`，随后进入 RAG、风险评估、条件转介、同辈话术检索和回复生成（`app/graph/workflow.py:41-91`）。
- 显式状态契约：`PsychologyGraphState` 覆盖会话、多模态输入、各 Analyzer 输出、RAG、风险、转介、回复、trace 与 `agent_judgments`，并用 `merge_dicts` reducer 处理并行写入（`app/graph/state.py:16-83`）。
- 多模态分析链路：文本分析、语音声学/MFCC/启发式/emotion2vec 辅助、端侧 MediaPipe 面部特征输入均已接入主图。白皮书将其总结为“文本 + 语音可用 + 端侧实时本地面部辅助”的多模态底座（`docs/whitepapers/2026-04-2-project-introduction-whitepaper.md:261-301`）。
- 双层 RAG：`rag_retriever` 面向风险案例，`peer_support_retriever` 面向同辈倾听话术；RAGFlow 客户端支持 Dify-compatible retrieval，失败时降级为空上下文（`app/rag/ragflow_client.py:37-114`）。
- 风险与转介：`risk_assessor` 已实现高危关键词/变体规则、LLM JSON 判断、声学轻度校准和高危强制转介；`referral_agent` 生成热线卡片并调度 webhook 告警（`app/nodes/risk_assessor.py:24-207`，`app/services/alert_service.py:45-86`）。
- 用户端联调原型：React 前端包含标准聊天、语音、视频通话、端侧面部分析开关、Trace 面板和 TTS 播放（`frontend/src/ChatInterface.jsx:14-145`）。
- 测试资产：当前本地统计后端 pytest 测试函数 130 个，前端 `node:test` 用例 26 个；白皮书也记录了 Graph、节点降级、WebSocket、RAG、emotion2vec、TTS、前端 helper 等覆盖范围（`docs/whitepapers/2026-04-2-project-introduction-whitepaper.md:390-412`）。

未完成部分主要不在“能否演示”，而在“能否进入真实校内试点”：生产级持久化、多实例运行、告警事件落库、人工接单回执、管理端看板、评测闭环、数据治理、部署脚本与 CI 仍未补齐。白皮书第 11 节已经列出这些试点前待补项（`docs/whitepapers/2026-04-2-project-introduction-whitepaper.md:464-500`）。

README 与白皮书之间的主要不一致已在 2026-05-22 同步修正：

- 前端测试数量统一为 26 个 `node:test` 用例。
- README 后续计划入口统一为本文件：`docs/plans/2026-05-22-project-diagnosis-and-development-plan.md`。
- 历史 `docs/plans` 文件删除是有意清理冗余文件，不再作为待恢复事项。
- Python 安装说明统一强调在 Conda 或其他隔离环境中运行，避免污染系统 Python。

## 2. 三个最大痛点

### 痛点 1：试点级状态、审计与告警闭环还没有真正落地

痛点描述：

系统已经能识别高风险、生成转介话术并触发 webhook，但从“发出告警”到“人工接单、升级、回执、结案、复盘”的闭环仍停留在模板和规划层。当前后端没有告警事件表、事件编号、处理状态、重试队列、人工接单接口、回执接口或管理端视图。

证据：

- 白皮书明确指出当前 `file` checkpointer 只适合单机验证，不适合多实例、高可用或集中运维，下一步要接 PostgreSQL、Redis、会话审计和回放（`docs/whitepapers/2026-04-2-project-introduction-whitepaper.md:468-475`）。
- `app/services/checkpoint_store.py` 仅实现 `memory` 与 `file`，选择 `postgres` 或 `redis` 会直接抛出缺少 saver 依赖的 RuntimeError（`app/services/checkpoint_store.py:84-101`）。
- `alert_service` 注释仍写着“Task 1 只做 mock”，真实 webhook 只返回 scheduled/sent 状态，没有事件持久化和业务状态机（`app/services/alert_service.py:1-4`，`app/services/alert_service.py:70-86`）。
- SOP 模板要求系统写入 `event_id`、触发时间、会话摘要、脱敏用户标识，并支持待处理、处理中、已接管、已结案等状态（`docs/rag/referral_sop_template.md:84-114`），但代码中尚未发现对应模型、路由和存储。

为什么是高优先级：

心理风险系统的核心不是“模型说 high”，而是 high 之后有没有可追踪的人类响应。没有 durable audit 和人工处置状态，高危事件可能在 webhook 失败、无人接单或多实例切换时丢失。这个问题直接决定能否进入校内小范围试点。

影响：

- AI Agent 技术能力：Agent 图已经能做判断，但缺少长期状态、事件溯源和 human-in-the-loop 状态机，无法形成可复盘的 Agent harness。
- 产品体验：学生端看似完成转介，但管理侧无法确认是否有人接住这次风险。
- 工程交付：单机 file checkpoint 和 mock webhook 无法支撑多实例部署、运维排障、伦理审查和事故复盘。

建议解决方向：

先不要继续堆新模态。优先实现 `alert_events` 与 `conversation_audit_events` 两类持久化对象，接入 PostgreSQL checkpointer，新增管理端告警列表、事件详情、接单/升级/结案 API，并让 `referral_agent` 写入 durable event 后再调度 webhook。短期目标是让每个 high 风险事件都有事件编号、状态、时间线和最小必要脱敏摘要。

### 痛点 2：评测闭环不足，风险策略还缺少可量化迭代机制

痛点描述：

项目已经有大量单元测试和接口契约测试，但这些测试主要验证“节点能运行、字段能返回、降级不崩”。对于心理风险识别的核心问题，即误报、漏报、边界表达、RAG 命中质量、提示词版本变更、模型切换后的风险分级变化，目前没有看到独立的离线评测 harness、黄金样本集、指标报表或人工复核回流机制。

证据：

- `docs/rag/risk_casebook_seed_v1_cases` 已经有 34 个种子风险案例，覆盖明确高危、失眠功能受损、考试压力、歌词引用、转述朋友风险等边界场景，但当前未看到把这些案例自动转为评测集并输出指标的脚本。
- `risk_assessor` 当前由关键词黑名单、变体正则、LLM JSON、声学校准和 RAG 上下文混合决策（`app/nodes/risk_assessor.py:24-207`）。这类混合策略如果没有离线评测，后续每次 prompt、模型或 RAG 变更都可能引入隐性回归。
- 白皮书建议增加误报/漏报复盘机制、Prompt 与输出审计记录、校内伦理与数据治理评审（`docs/whitepapers/2026-04-2-project-introduction-whitepaper.md:484-491`）。
- 现有测试数量可观，但白皮书描述的测试范围仍以 Graph、节点降级、WebSocket 事件、服务分支和前端 helper 为主（`docs/whitepapers/2026-04-2-project-introduction-whitepaper.md:397-412`），没有独立提到风险分类 benchmark 指标。

为什么是高优先级：

这个系统的成败取决于“高危不能漏、非高危不能乱升”。没有评测闭环，团队只能凭单次示例和人工感觉调规则，很难证明策略改动变好了，也无法向心理中心、伦理评审或信息化部门说明系统边界。

影响：

- AI Agent 技术能力：Agent 图缺少 harness engineering，不能把案例、模型、prompt、RAG、输出和指标串成闭环。
- 产品体验：误报会造成学生被过度打扰，漏报会造成真实风险被延迟响应。
- 工程交付：模型切换、本地大模型接入、RAG 知识库更新都会缺乏回归保护。

建议解决方向：

把 `docs/rag/risk_casebook_seed_v1_cases` 升级为 `evals/risk_cases/*.yaml` 或 `.jsonl`，字段包括输入、期望风险、允许理由、禁止行为、模态线索、是否应触发转介。新增 `scripts/run_risk_eval.py`，可在 mock LLM、当前 LLM、RAG on/off、voice/face on/off 组合下输出 precision、recall、false negative、false positive、边界案例列表和 trace 归档。后续每次 prompt、规则、模型、RAG 数据更新都必须跑评测。

### 痛点 3：产品完整性仍停留在学生端联调原型，缺少管理端和上线运营形态

痛点描述：

前端已经有聊天、语音、视频通话和 Trace 面板，但主要面向单个学生/演示者。正式试点需要的登录、角色权限、会话列表、告警看板、值班处理、人工回执、运营指标、部署监控和数据治理说明尚未落地。

证据：

- `frontend/src/App.jsx` 只渲染 `ChatInterface`，没有路由、登录态、角色区分或管理端入口。
- `ChatInterface` 主要由聊天、语音、面部开关、视频通话、TracePanel 组成（`frontend/src/ChatInterface.jsx:14-145`），适合联调和演示，不构成辅导员后台。
- 白皮书明确说当前前端适合联调和演示，要进入正式试点仍需补足登录与角色权限、会话列表和告警看板、管理端处理闭环、埋点与性能监控（`docs/whitepapers/2026-04-2-project-introduction-whitepaper.md:493-500`）。
- 仓库当前未发现 `.github/workflows`、Dockerfile 或 docker-compose；`.env.example` 仍以本地开发与 mock webhook 为主（`.env.example:25-38`）。
- WebSocket `final` 事件没有顶层 `risk_level` 和 `alert_status`，管理侧若复用实时通道只能从 `trace` 间接解析（`app/api/routes/ws_chat.py:165-174`）。白皮书也承认 REST 顶层稳定，WebSocket 主要通过 trace 暴露风险和告警信息（`docs/whitepapers/2026-04-2-project-introduction-whitepaper.md:79-85`）。

为什么是高优先级：

高校试点不是一个聊天窗口上线，而是学生端、辅导员端、心理中心、信息化运维、伦理审查之间的协作。缺少管理端和上线形态，会让项目停留在“技术演示好看”，但无法被真实组织采用。

影响：

- AI Agent 技术能力：Agent 的可解释 trace 只服务调试面板，没有进入运营观测、人工复核和案例回流。
- 产品体验：学生端可互动，辅导员端不可操作；高风险闭环无法被看见和管理。
- 工程交付：没有部署脚本、CI、健康检查和指标，交付成本和试点风险高。

建议解决方向：

短期先补最小管理端，不做复杂 CRM：一个 `/admin/alerts` 页面、告警列表、事件详情、接单/升级/结案按钮、trace 摘要、RAG 命中与最新证据。后端同步补管理 API 和单一管理员权限占位。部署上先用 docker-compose 起 FastAPI、前端、Postgres、Redis/RAGFlow 外部配置，并接入 CI 跑后端 pytest、前端 lint/build/node:test、风险 eval。

## 3. 后续开发计划

### 短期：1-2 周

目标：

把当前“可演示原型”硬化成“可被校内小范围试点评审”的最小闭环版本。重点不是新增能力，而是补齐事件持久化、评测基线、WebSocket 契约、CI 和文档一致性。

关键任务：

1. 文档入口与计划基线清理
   - 涉及文件：`README.md`、`docs/whitepapers/2026-04-2-project-introduction-whitepaper.md`、`docs/plans/2026-05-22-project-diagnosis-and-development-plan.md`
   - 动作：确认早期 `docs/plans` 文件删除为有意清理；README 与白皮书统一指向当前计划；不再恢复旧 hardening roadmap。
   - 验收标准：README 中后续计划链接可打开；白皮书版本更新到 V1.5；计划文档记录 2026-05-22 的确定决策。
   - 风险与依赖：若未来需要追溯早期计划，只从 git 历史查看，不再恢复到工作区。

2. 建立最小告警事件模型
   - 涉及模块：`app/models/schemas.py`、新增 `app/services/alert_event_store.py`、`app/nodes/referral_agent.py`、`tests/test_alert_service.py`、新增 `tests/test_alert_event_store.py`
   - 动作：定义 `alert_event_id`、`trigger_time`、`masked_session_id`、`risk_level`、`latest_risk_evidence`、`delivery_status`、`ack_status`、`handler_status`；事件状态采用 `created -> delivered -> acknowledged -> in_progress -> escalated -> closed`；先实现 file-backed 或 sqlite-backed store，避免第一周被数据库迁移阻塞。
   - 验收标准：高风险请求会生成稳定事件编号；事件写入本地 store；失败 webhook 也保留事件；测试覆盖 created、delivery_failed、acknowledged、closed。
   - 风险与依赖：真实用户身份映射和正式多角色权限暂不实现，先用 masked session 和单一管理员占位。

3. 修正 WebSocket final 契约
   - 涉及模块：`app/api/routes/ws_chat.py`、`tests/test_ws_chat.py`、前端 `frontend/src/hooks/useChatAgent.js`
   - 动作：在 `final` 事件中增加顶层 `risk_level`、`alert_status`、`alert_event_id`，保留 `trace` 兼容；高风险回合额外发送 `risk_event`，字段限定为 `alert_event_id`、`risk_level`、`handler_status`、`delivery_status`、`trace_id`、`masked_session_id`、`summary`。
   - 验收标准：文本 WS 和语音 WS 的最终事件均返回风险级别和告警状态；高风险事件能被管理端或外部系统按 `risk_event` 消费；前端 latestTrace 不受影响；旧字段兼容。
   - 风险与依赖：需谨慎维护现有前端逻辑和测试，避免破坏 TTS/token 流。

4. 建立风险评测 harness v0
   - 涉及模块：新增 `evals/risk_cases/*.yaml` 或 `.jsonl`、`scripts/run_risk_eval.py`、`tests/test_risk_eval_cases.py`
   - 动作：从 34 个 RAG seed case 抽取输入、期望风险、边界标签；先跑规则/节点级评测，不依赖真实 LLM；输出 JSON/Markdown 报告；标签采用“两层机制”：工程 baseline 先行，试点前再由心理中心或伦理评审抽检高风险、误报、漏报样本。
   - 验收标准：命令能输出总样本数、准确率、高危召回、误报列表、漏报列表；CI 中至少运行 mock 模式；评测报告明确区分 engineering baseline 与 expert-reviewed cases。
   - 风险与依赖：第一版标签不能被宣传为专业临床标注，只能作为工程回归基线。

5. 加最小 CI 与测试命令统一
   - 涉及文件：新增 `.github/workflows/ci.yml` 或本地 `scripts/ci_check.sh`、`README.md`、`frontend/package.json`
   - 动作：统一后端 pytest、前端 lint/build、前端 node:test、风险 eval 的命令；文档强调在隔离环境中运行。
   - 验收标准：一条命令可完成本地 smoke；CI 可跑不依赖真实模型/RAGFlow 的测试集。
   - 风险与依赖：当前依赖包含 torch、funasr、librosa 等重包，CI 可能需要拆 fast tests 与 optional integration tests。

6. 文档一致性修正
   - 涉及文件：`README.md`、白皮书、`.env.example`
   - 动作：统一前端测试数量 26；统一 TTS 模型命名；标注 postgres/redis 是预留不是已完成；明确 `.env.example` 中 mock webhook 不能代表真实告警闭环；记录完整对话允许保存、原始视频不保存、原始音频默认不长期保存的策略。
   - 验收标准：README、白皮书和代码事实一致；未完成能力均标记为待确认或下一阶段。
   - 风险与依赖：白皮书可能用于对外汇报，修改前需确认是否允许同步更新。

### 中期：1-2 个月

目标：

完成小范围校内试点所需的工程、Agent 评测和产品闭环：多实例持久化、管理端、人工处置流、观测指标、案例复盘和真实资源接入。

关键任务：

1. 接入生产级 checkpoint 与审计存储
   - 涉及模块：`app/services/checkpoint_store.py`、`app/core/config.py`、新增数据库迁移目录、`requirements.txt`
   - 动作：引入 `langgraph-checkpoint-postgres` 或等价实现；新增 Postgres 表保存 alert events、conversation audit events、prompt/output digest、trace reference。
   - 验收标准：`CHECKPOINT_BACKEND=postgres` 在 staging 可启动；重启后同一 `session_id` 能恢复会话；高危事件和 trace 可查。
   - 风险与依赖：数据库 schema 需要和数据最小化原则一起设计，避免保存过量敏感原文。

2. 建设辅导员/值班管理端 v1
   - 涉及模块：`frontend/src` 新增 admin 页面与路由、后端新增 `app/api/routes/admin_alerts.py`
   - 动作：实现单一管理员登录占位、告警列表、事件详情、接单、升级、结案、回执表单；事件详情展示风险证据、trace 摘要、RAG 命中、最近消息摘要。
   - 验收标准：高风险事件可从学生端触发并在管理端看到；管理员可更新状态；状态变化写入审计时间线。
   - 风险与依赖：真实组织流程未定，先由单一管理员承担值守人职责；正式试点时再拆分辅导员、心理中心和系统管理员。

3. 建立 Agent 评测与复盘闭环
   - 涉及模块：`evals/`、`scripts/run_risk_eval.py`、`app/prompts/`、`docs/rag/`
   - 动作：把 seed cases、真实脱敏复盘案例、误报漏报样本纳入评测；每个 prompt 版本关联评测结果；RAG 知识库更新后自动跑检索命中评测；专家抽检后的样本单独标记 `review_status=expert_reviewed`。
   - 验收标准：每次风险策略变更都有 baseline 对比；高危召回、非高危误报、RAG 命中、LLM JSON 解析失败率可见；expert-reviewed 子集可单独统计。
   - 风险与依赖：真实案例脱敏和标注需要伦理/数据治理流程。

4. 真实校园资源与 SOP 接入
   - 涉及文件：`docs/rag/referral_sop_template.md`、`docs/rag/referral_resource_qa_template.csv`、`app/nodes/referral_agent.py`
   - 动作：将模板替换为学校心理中心真实值班信息、升级矩阵、节假日规则；将热线卡片从硬编码改为 resource provider 或 RAG-backed resource resolver。
   - 验收标准：高风险卡片展示真实可用资源；告警 payload 包含事件编号、处置时限和首位责任岗位；资源变更不需要改代码。
   - 风险与依赖：真实联系方式和流程需校方授权；对外展示信息必须审核。

5. 可观测性与运营指标
   - 涉及模块：`app/services/trace_service.py`、新增 metrics/logging 中间件、前端 TracePanel/Admin dashboard
   - 动作：采集请求时延、模型时延、ASR/TTS 时延、RAG 命中、风险等级分布、告警送达率、人工接单时延、错误率。
   - 验收标准：本地/staging 能查看指标；高风险链路有端到端 trace id；故障可定位到 LLM/RAG/ASR/TTS/webhook/DB。
   - 风险与依赖：指标不能泄露敏感原文，需要只记录摘要、标签或 hash。

6. 数据保存、访问与删除策略
   - 涉及模块：新增数据治理文档、`app/services/alert_event_store.py`、审计存储、管理员端
   - 动作：默认保存完整对话文本和 ASR 转写 180 天；高风险事件摘要、处置状态、管理员回执和时间线保存 3 年；不保存原始视频；原始音频默认不长期保存，仅保存声学特征、转写和必要 trace。提供按 `session_id` / `alert_event_id` 导出与删除的管理员操作占位。
   - 验收标准：数据类型、保留期限、访问主体、删除路径写入文档并在代码配置中有对应常量或设置项；管理员端能查看审计摘要但不默认暴露过量原文。
   - 风险与依赖：正式期限需校内法务、伦理和信息安全确认；当前方案作为试点默认值。

7. 部署与环境硬化
   - 涉及文件：新增 Dockerfile、docker-compose、部署文档、`.env.example`
   - 动作：容器化 FastAPI 与前端；Postgres/Redis 外部化；模型服务、RAGFlow、BGE、emotion2vec 按 optional profile 配置；增加 health endpoints。
   - 验收标准：一份 staging compose 或部署脚本可以拉起核心服务；禁用外部模型时仍可跑 mock smoke；健康检查覆盖 DB、checkpoint、RAG、TTS、ASR。
   - 风险与依赖：本地深度模型资源较重，需把核心应用和模型推理解耦部署。

### 长期：3-6 个月

目标：

把系统从“试点可用”推进到“可运营、可评估、可治理的校园心理支持智能辅助底座”，形成与普通心理聊天系统的明确差异化。

关键任务：

1. 本地大模型与多模型路由
   - 涉及模块：`app/services/llm_client.py`、`app/core/config.py`、评测 harness
   - 动作：接入 A40 上的 Qwen2.5/3 本地推理接口；按任务路由模型：风险评估优先稳定低温模型，回复生成可用更强表达模型，摘要/审计用轻量模型。本任务明确放在 3-6 个月阶段，不阻塞短中期试点硬化。
   - 验收标准：本地模型在核心 eval 上达到或超过云端 baseline；模型不可用时自动降级；每个模型版本有评测记录。
   - 风险与依赖：GPU 资源、推理延迟、并发和模型安全策略需要压测。

2. 多 Agent 编排从固定图升级为策略化 harness
   - 涉及模块：`app/graph/workflow.py`、`app/graph/routers.py`、`app/services/trace_service.py`
   - 动作：保留主图确定性，但增加策略层：按输入模态、风险不确定性、RAG 置信度决定是否二次评估、是否请求人工复核、是否调用资源 resolver。
   - 验收标准：中风险或不确定样本可进入 second opinion 节点；trace 中能解释为什么加跑某个 Agent；评测能比较策略前后效果。
   - 风险与依赖：策略层不能让高风险路径变复杂到不可解释，必须保留强制转介规则。

3. 长期记忆与隐私分层
   - 涉及模块：checkpoint、用户画像、审计存储、数据治理文档
   - 动作：区分短期对话记忆、长期支持偏好、风险事件审计和不可持久化敏感原文；引入数据保留期限、删除请求、访问审计。
   - 验收标准：不同数据类型有明确存储位置、保留周期和访问权限；后台能导出审计但不暴露过量原文。
   - 风险与依赖：需校内法务/伦理/信息安全评审。

4. 多模态时序建模
   - 涉及模块：`app/nodes/voice_analyzer.py`、`app/nodes/face_analyzer.py`、前端 face/audio stream、evals
   - 动作：从单 segment/utterance 观察升级到跨回合时序趋势，如声学能量持续下降、长时间沉默、面部紧绷持续时间；仍保持“不可单独触发 high”的安全约束。
   - 验收标准：trace 展示趋势而非单点；中风险校准效果在评测中改善；没有引入面部/语音单独升 high 的路径。
   - 风险与依赖：多模态情绪推断误差高，必须以辅助证据定位，不能扩大为诊断。

5. 校园运营看板与质量复盘
   - 涉及模块：管理端、metrics、evals、RAG 数据管理
   - 动作：建立周/月报：会话量、风险分布、告警响应时延、误报漏报复盘、RAG 知识库更新、SOP 变更记录。
   - 验收标准：试点负责人能用看板回答“系统发现了多少、接住了多少、哪里失败了、下一步怎么改”。
   - 风险与依赖：指标展示要避免对学生群体做标签化或排名化。

6. 商业化与交付准备
   - 涉及模块：部署文档、权限体系、数据治理包、演示环境、学校配置模板
   - 动作：沉淀学校接入 checklist：组织角色、值班表、热线资源、数据保留、部署方式、RAGFlow 导入、应急预案、培训材料。
   - 验收标准：新学校可以按模板在 1-2 周内完成非生产演示接入；正式试点前有清晰验收清单。
   - 风险与依赖：不同学校制度差异大，需要配置化而不是硬编码流程。

## 4. AI Agent 技术突破建议

1. Harness engineering 要成为下一阶段主线

当前项目已经有 Agent 图，但还缺少围绕 Agent 的实验台。建议建立统一 harness：输入案例、运行配置、模型版本、prompt 版本、RAG 数据版本、节点输出、trace、最终风险、人工标注和指标全部可复现。这样项目的技术壁垒会从“有多个 Agent”升级为“能持续证明多个 Agent 的协作质量”。

2. 多 Agent 编排保持确定性，策略层只处理不确定性

高风险路径必须继续由 `risk_assessor -> risk_router -> referral_agent` 强制约束。创新点可以放在不确定性处理：中风险边界样本触发 second opinion；RAG 低置信度触发规则优先；LLM 输出漂移触发 fallback；高风险永远不能被声学或面部信号单独推导，也不能被 RAG 降级。

3. Prompt 与规则需要版本化

`app/prompts` 已集中管理提示词，这是好基础。下一步应为每个 prompt 增加版本号、变更说明、关联 eval 报告和审核记录。风险提示词尤其要有“允许 high / 禁止 high / 边界表达”测试清单。

4. 记忆系统要分层

不要把所有状态都塞进 checkpoint。建议分为：

- 会话运行态：LangGraph checkpoint。
- 风险事件态：alert event store。
- 审计态：conversation audit events 与 prompt/output digest。
- 用户偏好态：只有获得授权后才保存的长期偏好。
- 不可持久化态：原始视频与默认关闭长期保存的原始音频。完整对话文本允许保存，但必须纳入审计权限、保留期限和删除流程。

5. Trace 从调试面板升级为可观测协议

当前 `trace` 已包含 emotion2vec、面部观察、风险校准和 agent judgments。下一步应形成稳定 trace schema，用于管理端、eval 报告和故障定位。trace 中每个节点应包含：输入摘要、输出摘要、耗时、降级状态、外部依赖状态、版本信息。

6. 工具调用与外部系统接入要有安全边界

RAGFlow、webhook、TTS、ASR、LLM 都应被视为工具。每个工具要有 timeout、重试、降级、审计和最小数据原则。特别是告警 webhook 不能发送完整对话，只发送处置必要摘要、风险证据和事件编号。

7. 安全与隐私建议前置为工程约束

项目已经做了端侧人脸处理和高危规则兜底。下一步需要把这些原则落到测试和 CI：测试应断言 face/voice 不会单独升 high，断言高危明确表达必触发 referral，断言告警 payload 不含完整 session_id、手机号、学号等敏感字段。

## 5. 产品完整性建议

1. 第一版目标用户先收敛为两类路径

- 学生：进入文字/语音/视频陪伴，获得温和回应和必要转介资源。
- 单一管理员：看到高风险摘要，接单、升级、回执、结案，维护最小资源配置。

当前只完成了学生端联调路径，单一管理员路径是产品完整性的关键缺口。辅导员、心理中心负责人、系统管理员等多角色拆分放到真实校内 SOP 明确后的第二阶段。

2. 核心场景要从“一次对话”扩展为“一次事件”

正式试点的基本单位不应只是 message 或 session，而应是 alert event。一次事件要包含：触发、送达、接单、人工联系、升级、接管、回执、结案、复盘。这样才能支撑高校组织流程。

3. 交互闭环要减少黑箱感

学生端不应展示过多风控细节，但可以展示“我会陪你，同时建议联系现实支持”。辅导员端则需要看到风险证据、系统不确定性、RAG 参考和处理建议。TracePanel 目前偏开发调试，管理端需要的是“可执行摘要”。

4. 上线形态建议先做单校单院系灰度

不要一开始追求全校部署。建议以一个院系、一个入口、一个值班链路开始，明确试点期指标：高危召回、人工作用时延、告警送达率、误报处理成本、学生满意度、系统故障次数。

5. 运营与商业化准备要配置化

学校差异主要在值班表、联系人、升级顺序、热线资源、数据制度。应把这些做成配置和 RAG 资源，而不是写死在 `referral_agent`。交付包应包含 SOP 模板、资源 QA 模板、部署 checklist、伦理审查说明和培训材料。

## 6. 已收敛决策与关键开放问题

已收敛决策：

1. `docs/plans` 历史计划文件删除是有意清理，当前以本文件为计划基线；README 和白皮书已同步。

2. 真实校内 SOP 未确定前，默认采用单一管理员 SOP：系统创建高风险事件，记录事件编号与脱敏摘要，通知管理员；管理员接单后进入处理中，必要时升级，完成处置后填写回执并结案。

3. 允许保存完整对话文本和 ASR 转写。默认完整对话保留 180 天，高风险事件摘要、处置状态、管理员回执和时间线保留 3 年；原始视频不保存；原始音频默认不长期保存。

4. 第一版角色为学生端 + 单一管理员；多角色后台不是短期范围。

5. 风险评测采用工程 baseline + 专业抽检的两层方案。研发侧先维护可自动回归的 golden cases，心理中心/伦理评审后续抽检高风险、误报、漏报样本。

6. 本地大模型明确放入 3-6 个月能力扩展阶段。

7. WebSocket 最佳方案是稳定 `final` 顶层字段，并新增高风险 `risk_event` 事件；外部系统不得依赖 `trace` 内部调试结构。

仍需真实试点前确认的问题：

1. 学校心理中心真实联系人、值班时间、夜间链路、升级矩阵和最大响应时限。

2. 校内法务/伦理/信息安全对 180 天和 3 年默认保留期限是否接受，是否需要更短或分级保留。

3. 单一管理员账号在试点期由哪个岗位持有，是否允许多人共用，是否需要接入学校统一身份认证。

4. 原始音频是否存在研究保存需求；若需要，必须单独设计授权、开关、加密、访问审计和保留期限。
