# Text + Acoustic Fusion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 以规则化、保守、可追溯的方式，把文本与声学特征接到 `information_extractor` 和 `risk_assessor` 的辅助信号链路中。

**Architecture:** 保留现有文本主证据与高风险关键词兜底逻辑不变。先把原始声学特征转成中性的结构化观察项，再把这些观察项作为辅助证据注入节点输出、prompt 和 `agent_judgments`，并只对数值评分做有限校准，不允许单独触发高风险或诊断式结论。

**Tech Stack:** FastAPI, LangGraph, Python, numpy, pytest

---

### Task 1: 定义规则化声学观察项

**Files:**
- Modify: `app/nodes/information_extractor.py`
- Test: `tests/test_nodes.py`

**Step 1: Write the failing test**

新增测试，断言 `voice_acoustic_features` 会被转换成 `acoustic_observations` 和 `multimodal_summary` 的稳定结构。

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_nodes.py -k acoustic`

**Step 3: Write minimal implementation**

在 `information_extractor` 内添加规则函数，把停顿增多、语速占比偏低、能量波动异常等转成中性 observation code。

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_nodes.py -k acoustic`

### Task 2: 接入 risk_assessor 辅助信号链路

**Files:**
- Modify: `app/nodes/risk_assessor.py`
- Test: `tests/test_nodes.py`

**Step 1: Write the failing test**

新增测试，断言：
- benign 文本 + 声学异常不能触发 `high`
- medium 文本 + 声学支持可提升数值评分，但不突破等级边界
- `agent_judgments` 中保留 `acoustic_support_level`

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_nodes.py -k acoustic`

**Step 3: Write minimal implementation**

把 `acoustic_observations` 与原始特征摘要接入 prompt 和 `agent_judgments`，并对 `risk_score` 做有限校准：
- 不允许声学特征单独触发 `high`
- 不允许覆盖高风险关键词规则
- 只在 `low/medium` 边界内做小幅加权

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_nodes.py -k acoustic`

### Task 3: 同步文档与回归验证

**Files:**
- Modify: `README.md`
- Test: `tests/test_graph_integration.py`, `tests/test_chat_api.py`, `tests/test_ws_chat.py`

**Step 1: Update docs**

补充规则化融合边界、辅助信号用途和不可诊断说明。

**Step 2: Run regression suite**

Run: `conda run -n llm_env --no-capture-output python -m pytest -q tests/test_nodes.py tests/test_graph_integration.py tests/test_chat_api.py tests/test_ws_chat.py`

**Step 3: Verify expected outcome**

Expected: 所有相关测试通过，文本/语音主链路不回退。
