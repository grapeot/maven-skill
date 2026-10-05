# 会话与登录配置参考

本文档记录 Maven Agent Skill 的浏览器会话生命周期、环境配置、CDP 连接与隔离上下文细节，供 Agent 与维护者参考。

---

## 1. 系统依赖

- **Google Chrome**：本地运行环境中已安装系统级 Google Chrome（在系统 `PATH` 中或通过环境变量指定）。
- **Python 环境**：Python 3.12+ 虚拟环境，并已安装 `maven_skill` 包（提供 `maven-skill` CLI 工具）。
- **CDP 网络绑定**：Chrome DevTools Protocol (CDP) 仅监听本地回环地址 `127.0.0.1`，禁止外网暴露。

---

## 2. 环境配置与变量

CLI 支持通过命令行参数与环境变量进行配置。**CLI 不会自动读取 `.env` 文件**，配置需由外部 shell 或环境管理工具注入。

| 配置项 | 对应环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `--data-dir` | `MAVEN_DATA_DIR` | `.local` | 运行期数据存储目录。相对路径相对于执行命令时的当前工作目录（cwd）；跨目录调用请使用绝对路径。目录权限为 `0700` |
| `--port` | `MAVEN_CDP_PORT` | `9337` | Chrome CDP 远程调试监听端口（绑定 `127.0.0.1`） |
| *(无特定选项)* | `MAVEN_CHROME_EXECUTABLE` | 系统默认位置 | Google Chrome 可执行文件路径 |
| `--auth-state` | *(无)* | *(无)* | 全局选项，指定认证状态快照文件路径（必须写在子命令前） |

---

## 3. 会话命令语义 (`session`)

CLI 提供四个会话管理命令，执行结果统一输出标准 JSON：

### 3.1 `session open`
```bash
maven-skill session open [--url https://maven.com/]
```
- **语义**：唤起绑定独立持久 Profile（默认 `.local/browser-profile`）的 Chrome 实例，供人工完成登录。
- **复用行为**：若已有对应 CDP 端口的会话在运行，直接复用连接，且不覆盖用户当前停留在浏览器中的页面。

### 3.2 `session status`
```bash
maven-skill session status
```
- **语义**：检测 CDP 调试端口的通信连通性。
- **判定逻辑**：
  - 返回包含 `browser_connected: true` 时，表明 CDP 调试通信正常。
  - 若连接失败或超时，返回错误或连接失败状态。
- **重要约束**：`status` 仅代表本地 CDP 调试端口可达，**不代表 Maven 平台已处于登录状态**，不可假定凭证有效。

### 3.3 `session save`
```bash
maven-skill session save
```
- **语义**：从当前运行的浏览器中导出 Cookies、localStorage 与 IndexedDB 状态，保存至快照文件（默认 `.local/auth-state.json`）。
- **权限安全**：快照文件包含敏感凭据，严格以 `0600` 权限存储。

### 3.4 `session close`
```bash
maven-skill session close
```
- **语义**：先自动调用 `session save` 保存当前认证状态快照，随后安全关闭 Chrome 浏览器进程。

---

## 4. 隔离上下文模式 (`--auth-state`)

CLI 支持通过已存储的认证状态快照在独立上下文中执行命令：

```bash
maven-skill --auth-state .local/auth-state.json courses list
```

### 运行机制与约束
- **位置约束**：全局选项 `--auth-state` **必须放置在子命令之前**。
- **执行方式**：在已有 CDP 浏览器中建立临时独立 Context 执行数据提取，命令执行完毕立即销毁临时 Context，不影响浏览器中其他标签页。
- **实测结果与实验路径说明**：
  - **实测 Maven 会清除传入新 context 的认证 cookie，即使刚执行 `session save`**。
  - 该选项属于**实验路径**，不保证跨 context 的可移植登录。
  - 遇到快照失效时，CLI 必须明确报告 snapshot 认证未通过；**严禁将 profile 验收冒充 snapshot 成功**，**严禁将匿名 context 的状态写回有效快照文件**。
  - 常规任务默认使用持久 Profile（该路线已通过关闭 Chrome 重启后的登录复用验收）。若快照失败，应省略 `--auth-state` 回退到持久 Profile 路线继续。

---

## 5. 屏幕共享与 Headless 运行

- 人工登录与常规使用默认开启可见 Chrome 窗口。
- 在用户屏幕共享等敏感场景下，为了避免暴露浏览器可见窗口，可使用经用户授权的本地临时 wrapper 启动 headless Chrome（如注入 `--headless=new` 参数），并经由 `MAVEN_CHROME_EXECUTABLE` 指定。该 wrapper 复用同一持久 profile 和 CDP 端口。
- **不要永久修改 CLI 默认值**，保持公开 CLI 默认行为不变。

---

## 6. 安全红线与错误脱敏

- **去密错误提示**：网络异常、会话断开或页面结构变化时，CLI 错误输出必须经过脱敏处理，严禁在 stdout、stderr 或日志中暴露 Cookie、Authorization Token 等敏感凭据。
- **零 PII 原则**：会话与调试输出中不得记录任何真实用户个人身份信息。
