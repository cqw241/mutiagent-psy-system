### 分支角色定义
- **`master` (或 `main`)**：仅存放经过严格测试的生产级代码，严禁直接推送。
- **`develop`**：开发主分支，用于集成所有已完成的特性，严禁直接推送。
- **`feature/*`**：特性开发分支，所有新功能必须在此类分支开发。
- **`hotfix/*`**：紧急修复分支。
- **`release/*`**：发布准备分支。
### 提交规范 (Commit Message Convention)
项目强制执行 **Conventional Commits** 规范。不符合规范的提交将被本地 Git Hook 拦截。
- **豁免情况**：自动生成的 **Merge**（合并）和 **Revert**（回退）提交不受此规范限制。
- **格式**：`<type>(<scope>): <description>`
- **常见类型**：
    - `feat`: 新功能
    - `fix`: 修复 Bug
    - `docs`: 文档更新
    - `style`: 代码格式变动
    - `refactor`: 重构
    - `perf`: 性能优化
    - `chore`: 其他变动

---