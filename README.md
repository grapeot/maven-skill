# Maven Skill

Maven Skill 是面向 AI Agent 的 Maven 平台浏览器自动化工具与 Agent 技能包。基于 Playwright 驱动系统级 Google Chrome，以“浏览器优先、人工登录、Agent 观察”为核心设计，为后续自动化获取课程、Cohort 与学员报表提供底层会话连接支持。

> **当前阶段说明**：当前版本仅提供会话（Session）与 CDP 连接基础设施。Maven 平台具体的页面结构、选择器（Selectors）、Cohort 列表接口以及 CSV 下载流程尚未经过实机测试验证，暂不提供特定业务命令。

---

## 核心设计与特性

- **浏览器优先 (Browser-First)**：通过独立的持久化 Chrome Profile 让用户在真实浏览器界面中完成安全登录，避免逆向未知或频繁变动的认证流程。
- **持久化 Profile 作为主要登录态**：将用户登录凭据与会话维持在本地独立的浏览器数据目录中（默认 `.local/browser-profile`）。
- **可移植认证快照 (辅助机制)**：支持导出包含 Cookies、localStorage 与 IndexedDB（不包含 sessionStorage）的结构化快照 `.local/auth-state.json`，供离线备份与状态检查。*注：目前尚未验证将该快照载入全新浏览器的恢复有效性，未将其作为可用命令提供。*
- **解耦的进程模型**：Chrome 作为独立进程运行并通过本地 Chrome DevTools Protocol (CDP) 暴露控制端口，Agent 可随时通过 CDP 接入与脱离，不干扰浏览器常规运行。
- **严格的安全隔离**：CDP 仅监听本地回环地址（`127.0.0.1`）；核心运行数据与状态文件严格限制在本地目录；不向公开代码库泄露任何运行时数据。

---

## 环境要求

- Python 3.12+
- 系统已安装 Google Chrome
- 包管理与运行工具：推荐使用 `uv`

---

## 安装与初始化

1. 创建并激活虚拟环境：
   ```bash
   uv venv --python 3.12
   source .venv/bin/activate
   ```

2. 安装本地可编辑包及开发依赖：
   ```bash
   uv pip install -e '.[dev]'
   ```

3. 运行离线单元测试：
   ```bash
   pytest
   ```

---

## 配置与环境变量

CLI 支持全局命令行参数与环境变量注入。请注意：**CLI 工具不会自动加载 `.env` 文件**，配置需通过 shell 环境变量或外部环境管理器注入。

| 命令行选项 | 对应环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `--data-dir` | `MAVEN_DATA_DIR` | `.local` | 运行期数据存放目录（包含 Profile 与快照） |
| `--port` | `MAVEN_CDP_PORT` | `9337` | Chrome CDP 远程调试监听端口 |
| *(无特定选项)* | `MAVEN_CHROME_EXECUTABLE` | 系统默认路径 | 可选的 Google Chrome 可执行文件自定义路径 |

---

## 命令行接口 (CLI)

CLI 统一入口为 `maven-skill`，所有命令均返回结构化 JSON 输出。

### 会话管理命令 (`session`)

- **打开会话**：
  ```bash
  maven-skill session open [--url https://maven.com/]
  ```
  启动持久化 Chrome 实例并监听指定的 CDP 端口。若指定 URL，将在启动时加载（默认打开 Maven 首页）；如果连接到已有会话，则不会覆盖浏览器当前正在浏览的页面。

- **检查会话状态**：
  ```bash
  maven-skill session status
  ```
  检查 CDP 端口连通性。**注意**：`status` 输出仅代表浏览器调试端口可正常连接，不代表用户在 Maven 平台上已完成登录或登录态有效。

- **保存认证快照**：
  ```bash
  maven-skill session save
  ```
  从当前运行的浏览器中导出 Cookies、localStorage 和 IndexedDB 存储到 `.local/auth-state.json`（文件权限设为 `0600`）。

- **关闭会话**：
  ```bash
  maven-skill session close
  ```
  先自动执行状态保存，随后安全终止对应的 Chrome 进程。

### 页面观察命令 (`page`)

- **捕获页面文本快照**：
  ```bash
  maven-skill page snapshot
  ```
   提取最后一个 Maven 标签页的页面文字与控件信息，不保证它是前台活跃标签页。快照最多包含 30,000 字符与 300 个控件，截断结果不能当成完整名单。内容可能包含敏感业务信息或学员名单。

- **页面导航**：
  ```bash
  maven-skill page goto <URL>
  ```
   驱动最后一个 Maven 标签页跳转至目标 URL，仅允许 Maven 域名的 HTTPS 链接。目标地址应来自实际页面链接。

---

## 安全与隐私规范

- **回环端口限制**：CDP 控制端口等同于浏览器最高权限，严格限定在 `localhost` / `127.0.0.1` 监听。
- **文件系统权限**：数据目录权限默认设为 `0700`，认证快照文件权限设为 `0600`。
- **文件忽略规则**：`.local/` 目录、所有下载文件、运行日志、`.env` 文件均已加入 `.gitignore`，严禁提交到代码仓库。
- **只读操作边界**：本工具设计为只读观察与报表导出。严禁修改课程或学生数据，严禁发送邀请，严禁调用任何写入接口。任何业务写入必须获得独立显式授权。
- **公开示例约束**：公共仓库中仅包含虚拟生成的假数据示例（fake examples）。

---

## AI Agent Skill 安装说明

将本仓库的 GitHub URL 提交给 Codex、Claude Code、Cursor 或 OpenCode 等 AI Agent，并引导其按目标宿主工作区的规范完成安装：

1. 查阅目标工作区的 `AGENTS.md`、`CLAUDE.md` 或路由索引（如 `rules/skills/INDEX.md`）。
2. 将唯一根技能指向 `skills/maven/SKILL.md`。
3. 任何与私有账号别名、本地绝对路径相关的配置，均应在宿主环境自有的私有 overlay 中维护，避免硬编码至公共技能中。
