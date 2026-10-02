# RFC: Maven Skill 会话架构与设计说明

- **作者**：Maven Skill 设计组
- **状态**：Draft / Proposed
- **日期**：2026-10-02

---

## 1. 摘要与背景

Maven Skill 用于观察 Maven（maven.com）平台的课程信息、Cohort 进展及下载 CSV 报表。为适应不同页面任务与平台改版，本 RFC 采用真实 Google Chrome 实例的浏览器优先会话管理模型。官方 API 的可用范围尚未核实。

本 RFC 重点界定**运行态会话 (Session)**、**持久化配置 (Profile)** 与**认证状态快照 (Auth State)** 三者之间的概念边界与实现权衡，并阐明未来的 UI 交互迭代路线。

---

## 2. 核心架构设计

### 2.1 整体分层架构

```
┌────────────────────────────────────────────────────────┐
│                      AI Agent                          │
│        (Codex / Claude Code / Cursor / OpenCode)       │
└──────────────────────────┬─────────────────────────────┘
                           │ CLI 调用 (JSON 交互)
                           ▼
┌────────────────────────────────────────────────────────┐
│                   maven-skill CLI                      │
│        (Python 3.12+ / argparse / Playwright 客户端)    │
└──────────────────────────┬─────────────────────────────┘
                           │ CDP (Chrome DevTools Protocol)
                           │ http://127.0.0.1:9337
                           ▼
┌────────────────────────────────────────────────────────┐
│                 Google Chrome (独立进程)                │
│  - 监听: 127.0.0.1:9337 (严格回环绑定)                 │
│  - 数据目录: .local/browser-profile (0700 权限)          │
│  - 人工完成登录，状态原生持久化于磁盘                      │
└────────────────────────────────────────────────────────┘
```

### 2.2 三大状态载体的概念与职责边界

在设计浏览器自动化工具时，必须清晰区分三种不同层面的“状态”：

| 维度 | 运行态会话 (Session) | 持久化配置 (Browser Profile) | 便携认证快照 (Auth State) |
|---|---|---|---|
| **物理表现** | 正在运行的 Chrome 操作系统进程 | 本地磁盘目录（`.local/browser-profile`） | 单个 JSON 文件（`.local/auth-state.json`） |
| **生命周期** | 从 `session open` 到 `session close` | 长期持久存在于本地磁盘 | 每次执行 `session save` 时原子替换 |
| **所含内容** | 内存中的标签页、DOM 树、网络连接、CDP 管道 | 全量浏览器状态（Cookies、Cache、IndexedDB、证书、插件配置） | 提取的 Cookies、localStorage、IndexedDB（**不含 sessionStorage**） |
| **定位与权衡** | Agent 交互的控制管道 | **主要登录态载体**，原汁原味维持登录状态 | **辅助可移植快照**，用于检查与离线备份 |
| **有效性保证** | 仅在进程存活期有效 | 保留本机浏览器状态；能否跨重启登录需实测 | 不保证长期有效或跨设备恢复 |
| **当前实现状态**| 已实现进程管理与 CDP 连接复用 | 已实现独立目录隔离与权限设置 | 已实现状态提取导出；**暂未实测加载至全新浏览器的能力，不暴露导入命令** |

#### 权衡分析：为何以 Persistent Profile 为主，而非纯 State JSON？
Persistent Profile 保留同一个本机浏览器的状态，避免每次启动重新拼装凭证。Storage State 只覆盖 cookies、localStorage 和可选 IndexedDB，不是完整 profile。两者都无法延长服务端会话寿命；跨重启登录效果需要用户登录后验证。

---

## 3. CDP 控制面与进程模型

### 3.1 独立进程与守护
- 执行 `maven-skill session open` 时，工具以后台方式派生出独立的 Google Chrome 进程，并附加参数：
  ```
  --user-data-dir=.local/browser-profile
  --remote-debugging-port=9337
  --no-first-run
  --no-default-browser-check
  ```
- 进程与发起该命令的 Python 脚本脱钩，避免脚本执行完毕后浏览器被意外销毁。
- 当再次调用 `session open` 时，工具先探测目标端口。若已有存活的 Chrome 实例，则直接复用现有连接，**坚决不执行导航或覆盖操作**，以避免破坏用户正在人工操作的上下文。

### 3.2 状态探测 (`session status`) 语义约束
- `session status` 的技术实现为向 `http://127.0.0.1:<PORT>/json/version` 发起 HTTP GET 请求。
- 返回 `browser_connected: true` 仅代表 Chrome 调试服务可连通；连接后还核验 `Browser.getBrowserCommandLine` 中的 profile 路径，拒绝误接其他浏览器。登录有效性必须依赖实际页面观察。

### 3.3 退出契约 (`session close`)
- 执行关闭操作时，为防止用户最新交互产生的重要凭据丢失，CLI 会通过 Playwright 客户端先发起一次 `session save`，将当前上下文状态持久化至 `.local/auth-state.json`，随后再发送关闭指令退出 Chrome 进程。

---

## 4. 安全与权限架构

1. **严格的回环绑定 (Loopback Only)**：
   CDP 协议拥有任意执行 JavaScript、捕获网络流量与下载文件的特权。任何情况下，调试端口严禁绑定至 `0.0.0.0`，只能监听 `127.0.0.1`。
2. **Unix 文件权限管控**：
   - Profile 目录（`.local/browser-profile`）及父目录权限严格设为 `0700`（仅当前宿主用户可读写执行）。
   - 导出的认证状态文件（`.local/auth-state.json`）权限严格设为 `0600`（仅当前宿主用户可读写）。
3. **版本库防泄密**：
   `.gitignore` 必须将 `.local/`、所有的临时下载文件、日志文件与 `.env` 完整隔离，防止带凭证代码意外外发。

---

## 5. 后续 UI 交互与业务迭代规划 (Future UI Iteration)

当前版本聚焦于稳定会话底座。后续演进将按照以下阶段推进：

```
[Phase 1: 当前] ──► [Phase 2: 页面探测] ──► [Phase 3: 列表解析] ──► [Phase 4: CSV 流式导出]
 Session / CDP        DOM 稳定性走查         Cohort 分页遍历         下载拦截与内容校验
```

### 5.1 页面探测 (Phase 2)
- 在实机环境中人工登录 Maven，走查 Dashboard 主视图。
- 确立稳定的登录态特征选择器（例如右上角个人头像或主导航栏），为 `session status` 增加深度的页面级有效性验证。

### 5.2 Cohort 列表解析 (Phase 3)
- 调研 Maven 课程下的 Cohort 展示形式（判断其属于标准分页组件、无限滚动列表还是服务端渲染单页）。
- 实现自动翻页机制，并在提取数据时显式标注数据范围与完整性元数据（例如总页数、已抓取页数）。

### 5.3 报表 CSV 导出 (Phase 4)
- 探索报表下载按钮的交互模式（直接链接触发 vs 异步生成导出）。
- 实现下载流拦截，将文件统一保存至私有本地目录，并在完成后进行 MIME 与内容格式校验，确保下载产物是真实有效的 CSV 数据，而非重定向后的 HTML 报错页。
