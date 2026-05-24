# Git 规则：GitHub Flow

本仓库采用 **GitHub Flow**，而不是 GitFlow。核心原则是：`main` 是唯一长期主干，所有改动都通过短生命周期分支和 Pull Request 合入。

## 1. 核心原则

- `main` 必须始终保持可运行、可演示、可回滚。
- 禁止直接向 `main` 推送业务改动，所有改动必须通过 Pull Request。
- 不使用长期 `develop` 分支。
- 不使用长期 `release/*` 分支。
- 紧急修复也从 `main` 拉短分支，通过 PR 合入。
- 分支生命周期要短：一个分支只解决一个明确问题，合入后立即删除。

## 2. 分支命名

从最新 `main` 拉取新分支：

```bash
git checkout main
git pull origin main
git checkout -b <type>/<short-topic>
```

允许的分支类型：

- `feature/<short-topic>`：新功能，例如 `feature/admin-alert-list`
- `fix/<short-topic>`：缺陷修复，例如 `fix/ws-risk-event`
- `docs/<short-topic>`：文档更新，例如 `docs/github-flow-rules`
- `chore/<short-topic>`：工程维护，例如 `chore/ci-cache`
- `refactor/<short-topic>`：不改变外部行为的重构
- `experiment/<short-topic>`：短期实验，只能用于验证思路，不长期保留

命名要求：

- 使用英文小写、数字和短横线。
- 名称要表达目的，不使用 `test`、`update`、`tmp` 这类模糊名称。
- 一个分支只承载一个目标，避免把功能、重构、格式化和文档混在一起。

## 3. 标准开发流程

1. 同步 `main`

   ```bash
   git checkout main
   git pull origin main
   ```

2. 创建短分支

   ```bash
   git checkout -b feature/example-topic
   ```

3. 小步提交

   - 每个 commit 应表达一个独立意图。
   - 不提交无关格式化、临时文件、调试输出或本地环境文件。
   - 不回滚他人未确认的改动。

4. 本地验证

   根据变更类型运行最小充分验证：

   - 文档改动：检查链接、文件路径、术语一致性。
   - 后端改动：运行相关 `pytest` 或项目约定的后端检查。
   - 前端改动：运行相关 `node:test`、lint 或 build。
   - Agent、风险、告警、隐私相关改动：必须补充或运行对应回归用例。

5. 推送分支

   ```bash
   git push -u origin feature/example-topic
   ```

6. 创建 Pull Request

   PR 描述必须说明：

   - 本次解决的问题。
   - 主要改动范围。
   - 已运行的验证命令和结果。
   - 风险、限制和回滚方式。

7. 合入 `main`

   - CI 必须通过。
   - Review 意见必须处理或明确说明不采纳原因。
   - 默认使用 Squash merge，保持 `main` 历史清晰。
   - 合入后删除远端分支。

## 4. Commit Message 规范

项目采用 **Conventional Commits**：

```text
<type>(<scope>): <description>
```

常用 `type`：

- `feat`：新功能
- `fix`：缺陷修复
- `docs`：文档更新
- `test`：测试新增或调整
- `refactor`：不改变行为的重构
- `perf`：性能优化
- `style`：格式调整，不改变逻辑
- `chore`：工程维护
- `ci`：CI/CD 配置
- `revert`：回退提交

常用 `scope`：

- `graph`：LangGraph 编排
- `nodes`：Agent 节点
- `risk`：风险识别与分级
- `alerts`：告警与人工处置闭环
- `rag`：RAG 与知识库
- `ws`：WebSocket 协议
- `api`：HTTP API
- `frontend`：前端用户界面
- `evals`：评测与回归基线
- `docs`：项目文档
- `ci`：持续集成

示例：

```text
feat(alerts): persist high risk alert events
fix(ws): include risk event id in final payload
docs(git): rewrite rules for github flow
test(risk): add baseline cases for high risk recall
```

## 5. Pull Request 合入门槛

PR 必须满足以下条件才能合入：

- 分支基于最新 `main`。
- 改动范围清晰，没有混入无关文件。
- CI 通过，或在 PR 中说明无法运行的原因。
- 已运行与改动匹配的本地验证。
- 文档、配置、测试与代码行为保持一致。
- 对用户体验、数据保存、隐私、安全、风险分级或告警链路有影响的改动，必须在 PR 中明确说明影响面。

以下情况不得合入：

- 直接绕过失败测试。
- 为了通过测试而删除关键断言。
- 将真实密钥、隐私数据、原始学生数据或本地 `.env` 提交到仓库。
- 在同一个 PR 中混入大规模无关重构。
- 改写已经推送到共享远端的公共历史。

## 6. `main` 保护规则

推荐在 GitHub 仓库中开启以下保护：

- 禁止直接 push 到 `main`。
- 要求 Pull Request 才能合入。
- 要求 CI 通过。
- 要求至少一次 Review。
- 合入前要求分支与 `main` 保持同步。
- 禁止 force push。
- 禁止删除 `main`。

## 7. 发布与回滚

GitHub Flow 中，`main` 合入即代表具备部署资格。发布通过 tag 或 GitHub Release 标记：

```bash
git tag v0.1.0
git push origin v0.1.0
```

回滚优先使用 `git revert`，不要改写公共历史：

```bash
git revert <commit-sha>
git push origin main
```

如果问题来自已合入 PR，应创建新的修复 PR 或 revert PR，并在描述中说明影响范围和恢复路径。

## 8. 协作边界

- 修改前先看当前工作区状态，避免覆盖他人或 Agent 已产生的改动。
- 发现无关脏文件时，不要擅自暂存、删除或回滚。
- 如果必须修改同一文件中的他人未提交内容，先确认改动意图，再做最小必要编辑。
- 文档类变更可以只做文档验证；代码类变更必须运行对应测试。
- 自动化 Agent 提交也必须遵守同样的分支、PR、验证和审计规则。
