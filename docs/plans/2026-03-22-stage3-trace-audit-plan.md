# Stage 3 Trace + Auditability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不破坏现有文本/语音 WebSocket 主流程的前提下，把声学辅助证据系统化写入 `agent_judgments` 和 trace 输出，并提供前端可视化调试面板所需的向后兼容数据。

**Architecture:** 保留“文本主证据优先、显式高风险文本兜底”的现有策略不变。新增一层轻量 trace 组装逻辑，把 `acoustic_observations`、`acoustic_support_level`、评分校准前后值、最新 voice segment 摘要汇总到可选 trace payload 中；前端只在有数据时显示调试面板，不改变已有聊天流和高风险卡片逻辑。

**Tech Stack:** FastAPI, LangGraph, React, WebSocket, Python, pytest

---

### Task 1: 定义可选 trace 数据结构

**Files:**
- Create: `app/services/trace_service.py`
- Modify: `app/graph/state.py`
- Modify: `app/models/schemas.py`
- Test: `tests/test_state_schema.py`

**Step 1: Write the failing test**

新增测试，断言状态和响应 schema 支持可选 `trace` 字段，且不影响现有必填字段。

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_state_schema.py -v`

Expected: FAIL，因为 `trace` 字段尚未定义。

**Step 3: Write minimal implementation**

在 `trace_service.py` 中定义 trace 组装函数和最小结构约定；在 state/schema 中新增可选 `trace` 字段。

建议 trace 顶层结构：

```python
{
    "latest_voice_segment": {...} | None,
    "acoustic_observations": list[str],
    "acoustic_support_level": "none" | "mild" | "notable",
    "risk_calibration": {
        "base_score": 0.6,
        "adjusted_score": 0.68,
        "risk_level": "medium",
        "used_acoustic_adjustment": True,
    },
    "agent_judgments": {...},
}
```

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_state_schema.py -v`

**Step 5: Commit**

```bash
git add app/services/trace_service.py app/graph/state.py app/models/schemas.py tests/test_state_schema.py
git commit -m "feat: add optional trace schema for audit output"
```

### Task 2: 系统化写入 agent_judgments 与 trace

**Files:**
- Modify: `app/nodes/information_extractor.py`
- Modify: `app/nodes/risk_assessor.py`
- Modify: `app/services/acoustic_fusion_service.py`
- Modify: `app/services/trace_service.py`
- Test: `tests/test_nodes.py`

**Step 1: Write the failing test**

新增测试，断言：
- `information_extractor` 会把 `acoustic_observations` 写入 `agent_judgments["information_extractor"]`
- `risk_assessor` 会把 `acoustic_support_level`、`base_score`、`adjusted_score`、`used_acoustic_adjustment` 写入 `agent_judgments["risk_assessor"]`
- benign 文本 + 声学异常仍不升到 `high`

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_nodes.py -k "trace or acoustic" -v`

Expected: FAIL，因为当前还没有系统化 trace / calibration 元数据。

**Step 3: Write minimal implementation**

在 `acoustic_fusion_service.py` 中把评分校准函数改成返回结构化结果，例如：

```python
{
    "base_score": 0.6,
    "adjusted_score": 0.68,
    "used_acoustic_adjustment": True,
}
```

在 `information_extractor.py` 和 `risk_assessor.py` 中：
- 保留原有高风险关键词兜底逻辑
- 记录声学观察项和支持强度
- 记录校准前后分数
- 不改变 `high` 的文本显式证据门槛

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_nodes.py -k "trace or acoustic" -v`

**Step 5: Commit**

```bash
git add app/nodes/information_extractor.py app/nodes/risk_assessor.py app/services/acoustic_fusion_service.py app/services/trace_service.py tests/test_nodes.py
git commit -m "feat: capture acoustic support and risk calibration in judgments"
```

### Task 3: 将 trace 汇总到 REST / WebSocket 输出

**Files:**
- Modify: `app/api/routes/chat.py`
- Modify: `app/api/routes/ws_chat.py`
- Modify: `app/services/trace_service.py`
- Test: `tests/test_chat_api.py`
- Test: `tests/test_ws_chat.py`

**Step 1: Write the failing test**

新增测试，断言：
- `/chat` 响应可选携带 `trace`
- `/ws/voice-chat/{session_id}` 的 `final` payload 可选携带 `trace`
- `transcript` 事件仍保持原有 `text` / `segment_id` 等字段兼容

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_chat_api.py tests/test_ws_chat.py -v`

Expected: FAIL，因为路由层当前没有输出结构化 trace。

**Step 3: Write minimal implementation**

在路由层新增一个只读 trace 组装步骤，把状态中的以下内容合并到可选 `trace` 字段：
- `voice_segments`
- `multimodal_features.latest_voice_segment`
- `extracted_signals.acoustic_observations`
- `agent_judgments.information_extractor`
- `agent_judgments.risk_assessor`

兼容策略：
- 不新增必填字段
- 不改 `final.reply`、`referral_required`、`hotline_card`
- 只给 `final` 和 REST response 增加可选 `trace`

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_chat_api.py tests/test_ws_chat.py -v`

**Step 5: Commit**

```bash
git add app/api/routes/chat.py app/api/routes/ws_chat.py app/services/trace_service.py tests/test_chat_api.py tests/test_ws_chat.py
git commit -m "feat: expose optional trace payloads for rest and websocket"
```

### Task 4: 前端调试面板接入

**Files:**
- Modify: `frontend/src/ChatInterface.jsx`
- Optionally Modify: `frontend/src/hooks/useAudioStream.js`
- Test: `frontend` build smoke via `npm --prefix frontend run build`

**Step 1: Write the failing test/acceptance target**

这里用构建级验证代替单元测试：先确定 UI 行为目标。

目标：
- 当 `final.trace` 不存在时，前端行为与现在完全一致
- 当 `final.trace` 存在时，显示一个可折叠调试面板
- 面板只展示辅助证据和分数校准，不展示诊断式标签

**Step 2: Implement minimal UI**

在 `ChatInterface.jsx` 中新增一个轻量调试区，展示：
- 最新 `segment_id`
- `acoustic_observations`
- `acoustic_support_level`
- `risk_calibration.base_score -> adjusted_score`

兼容策略：
- 全部字段按 optional 读取
- 缺失则不渲染该模块
- 不改变现有消息列表、输入框和语音按钮交互

**Step 3: Run build verification**

Run: `npm --prefix frontend run build`

Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/ChatInterface.jsx
git commit -m "feat: add optional trace debug panel for voice support signals"
```

### Task 5: 文档与全链路回归

**Files:**
- Modify: `README.md`
- Test: `tests/test_nodes.py`
- Test: `tests/test_graph_integration.py`
- Test: `tests/test_chat_api.py`
- Test: `tests/test_ws_chat.py`
- Test: `tests/test_state_schema.py`

**Step 1: Update docs**

补充：
- trace 字段结构
- 前端调试面板显示内容
- 兼容策略（字段可选，不破坏旧前端）
- 明确“辅助证据 != 诊断/情绪分类”

**Step 2: Run regression suite**

Run:

```bash
conda run -n llm_env --no-capture-output python -m pytest -q \
  tests/test_nodes.py \
  tests/test_graph_integration.py \
  tests/test_chat_api.py \
  tests/test_ws_chat.py \
  tests/test_state_schema.py
```

以及：

```bash
npm --prefix frontend run build
```

**Step 3: Verify expected outcome**

Expected:
- 所有后端测试通过
- 前端构建通过
- benign 文本 + 异常声学仍不会触发 `high`
- `final` / REST trace 输出保持可选和向后兼容
