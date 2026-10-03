# AGENTS.md

本文档定义了 AI Agent 在维护、开发与扩展本仓库（`maven_skill`）时必须严格遵守的工程纪律与操作契约。

---

## 1. 仓库定位与版本控制纪律

- **公开开源代码仓库**：本仓库面向公开开源设计，远端仓库为 `https://github.com/grapeot/maven-skill`，基于 MIT 许可证。
- **分支保护规则**：`master` 主分支已开启保护规则，合并要求包括 Pull Request 流程、自动化测试检查（test check）通过、0 reviewers 且 `enforce_admins=true`。
- **严格授权约束**：
  - 未经人类用户明确显式指令，**严禁**执行 `git commit`、`git push`、创建额外远端仓库或推送至任何远程分支。
  - 严禁执行任何不可逆的清理或重置命令（如 `git reset --hard`、`git clean -fd`）。
- **干净的工作区**：严禁将任何个人凭证、生产环境配置、测试学员数据或个人工作笔记推入代码仓库。

---

## 2. Python 环境与依赖管理规范

- **虚拟环境隔离**：
  - 必须使用位于仓库根目录的 `.venv` 虚拟环境。
  - 若 `.venv` 不存在，使用 `uv venv --python 3.12` 进行初始化。
  - 在执行任何 Python 命令或依赖操作前，必须先激活虚拟环境：`source .venv/bin/activate`。
- **依赖管理方式**：
  - 使用 `uv pip install` 管理依赖，禁止使用全局 `pip install`。
  - 开发环境安装命令：`uv pip install -e '.[dev]'`。
- **自动化测试**：
  - 代码改动后使用 `pytest` 运行离线单元测试（包含 138 项核心测试与隐私安全断言）。
  - 单元测试严禁对真实的外部网络发出真实网络请求。

---

## 3. 隐私保护与安全边界

- **禁止硬编码敏感信息**：
  - 代码、文档与测试用例中严禁包含开发机绝对路径、真实邮箱地址、真实用户账号或内部私有域名与地址。
  - 所有示例数据必须采用虚拟占位符（fake examples）。
- **敏感文件与目录隔离**：
  - 运行期产生的数据目录（默认 `.local/`，包括 `browser-profile/`、`auth-state.json`、`downloads/` 及 `receipts/`）、临时日志文件及 `.env` 必须严格包含在 `.gitignore` 中。
  - 文件系统权限必须符合最小特权原则：目录 `0700`，凭证、导出 CSV、收据及状态文件 `0600`。
- **输出与页面快照脱敏**：
  - 页面观察命令（`maven-skill page snapshot`）所提取的页面文字可能包含真实学员信息，仅供本地分析，不得记录到长期公共文档或公开日志中。
  - 业务命令（`courses list`、`cohorts list`、`students export`、`lessons list/show/stats`）的 stdout 仅输出结构化状态与聚合计数，严禁打印学员姓名与邮箱。

---

## 4. 业务边界与事实原则

- **业务命令范围**：
  - 本仓库已实现 v0.1 只读业务 CLI（包括 `courses list`、`cohorts list`、`students export`）、Lightning Lesson 只读命令（`lessons list`、`lessons show`、`lessons stats`）与会话/页面基础设施。lessons 命令只导航和读取，不得新增任何点击或输入。
  - 命令实现基于真实 DOM 观察契约（从账号菜单动态路由至 Dashboard 与 Courses，交叉核验 Student home 与 settings 链接确定 Cohort slug，原生导出对话框筛选 Enrolled 学员）。
  - **不逆向私有 API**：保持浏览器优先策略，不逆向 Maven 私有接口。
  - **无 Ledger 耦合**：本仓库不包含任何 Ledger 业务规则或外部系统数据写入代码。
- **严格只读原则**：
  - Agent 在任何情况下不得擅自执行对 Maven 平台的数据变更操作（包括但不限于修改课程信息、修改学员状态、发送邮件邀请、调用记账或分润接口）。
  - 任何可能产生业务副作用的写操作，必须停下来获得用户的单独显式授权。
- **错误脱敏**：
  - 运行期捕获的异常信息在向 CLI 输出时必须经过脱敏处理，杜绝泄露 Token、Cookie 或内部路径等隐私数据。

---

## 5. 工作状态记录要求

- 每轮实质性修改或开发迭代后，必须同步更新 `docs/working.md`。
- 详细记录当前进度、实测验证项（Checklist）以及遇到的实际问题与解决方案，确保上下文可追溯。
