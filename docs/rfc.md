# RFC: Maven Skill 会话与业务交互架构设计

- **作者**：Maven Skill 设计组
- **状态**：Implemented / v0.1 Specification
- **日期**：2026-10-02

---

## 1. 摘要与背景

Maven Skill 用于观察 Maven（maven.com）平台的课程开设信息、班期（Cohort）排期及导出报名学员（Enrolled）CSV 报表。为抵御官方 API 范围未知及私有接口频繁变更的脆弱性，本设计采用真实 Google Chrome 实例与浏览器优先（Browser-First）会话管理模型。

本 RFC 界定**运行态会话 (Session)**、**持久化配置 (Profile)** 与**便携认证快照 (Auth State)** 三者职责，阐明已实现的 v0.1 业务交互契约（动态路径发现、班期识别、导出对话框控制与数据校验）及隔离执行模型。

---

## 2. 核心架构设计

### 2.1 整体分层架构

```
┌────────────────────────────────────────────────────────┐
│                      AI Agent                          │
│        (Codex / Claude Code / Cursor / OpenCode)       │
└──────────────────────────┬─────────────────────────────┘
                           │ CLI 调用 (结构化 JSON 交互)
                           ▼
┌────────────────────────────────────────────────────────┐
│                   maven-skill CLI                      │
│     (Python 3.12+ / Playwright 客户端 / ops / parse)    │
└──────────────────────────┬─────────────────────────────┘
                           │ Chrome DevTools Protocol (CDP)
                           │ http://127.0.0.1:9337 (仅限本地回环)
                           ▼
┌────────────────────────────────────────────────────────┐
│                 Google Chrome (独立宿主进程)             │
│  - 监听: 127.0.0.1:9337                                │
│  - 默认配置目录: .local/browser-profile (0700 权限)       │
│  - 人工完成登录，状态原生持久化于磁盘                      │
└────────────────────────────────────────────────────────┘
```

### 2.2 三大状态载体的职责与生命周期

| 维度 | 运行态会话 (Session) | 持久化配置 (Browser Profile) | 便携认证快照 (Auth State) |
|---|---|---|---|
| **物理表现** | 正在运行的 Chrome 操作系统进程 | 本地磁盘目录（`.local/browser-profile`） | 单个 JSON 文件（`.local/auth-state.json`） |
| **生命周期** | 从 `session open` 到 `session close` | 长期持久存在于本地磁盘 | 每次执行 `session save` 时原子替换写入 |
| **所含内容** | 内存中的标签页、网络连接、CDP 管道 | 完整的浏览器状态（Cookies、Cache、IndexedDB 等） | 导出的 Cookies、localStorage、IndexedDB（**不含 sessionStorage**） |
| **定位与职责** | 控制命令接入的实时管道 | **主要登录态载体**，保持原生会话维持 | **辅助可移植快照**，用于备份及独立 context 隔离执行 |
| **有效性保证** | 仅在进程存活期有效 | 保持本机浏览器状态；跨重启有效性待实测 | 取决于服务端 Cookie/Session 有效期，不可假定长期有效 |

---

## 3. 业务执行模型与隔离机制

### 3.1 默认执行模式（持久 Context + 独立工作标签页）
- 业务命令在已有 CDP 浏览器中执行时，默认通过 `browser.contexts[0]` 开辟全新的独立工作标签页（work tab）。
- 工作标签页完成页面导航、DOM 观察或报表导出后，在 `finally` 块中自动执行 `page.close()`。
- 该机制保证人类用户在浏览器中正在浏览的页面不被切换、覆盖或重载。

### 3.2 独立 Context 模式 (`--auth-state`)
- 当指定全局 `--auth-state <FILE>` 参数时（参数必须写在子命令前），CLI 会调用 `browser.new_context(storage_state=auth_state)` 建立完全隔离的临时上下文。
- 任务执行完毕后，临时上下文被显式关闭（`owned.close()`），不污染已有默认 profile 的运行环境。
- `--auth-state` 的隔离逻辑已在自动化离线测试中得到验证。

---

## 4. 业务 DOM 发现与交互契约

### 4.1 动态课程路径发现 (`courses list`)
- 为避免硬编码组织或租户路径，CLI 从 `https://maven.com/` 首页发起探测。
- 定位页面右上角账号菜单按钮（`button[aria-haspopup='menu']`）并触发点击。
- 从弹出菜单中读取指向 Dashboard 的超链接，导航至 Dashboard 页面。
- 从 Dashboard 中定位指向 `/admin/courses` 的 Courses 链接，进入课程管理视图。
- 去重收集课程列表观察到的管理链接与标题，支持链接型分页；其他分页控件报告 partial，不宣称结果全量或只包含 PUBLISHED 状态。

### 4.2 班期卡片解析与 `latest` 选期逻辑 (`cohorts list`)
- 导航至课程管理概览页，定位包含 `Student home` 的班期卡片。
- 对每个卡片，提取 `Student home` 链接中的 slug 以及对应 `settings` 链接中的 `cohort` 参数，双向核对一致后确认该班期的真实标识。
- 解析班期状态（`upcoming`、`self_paced` 或常规已排期），并提取日期区间与起始日期。
- **`latest` 判定算法**：
  1. 若存在唯一的 `upcoming` 班期，直接判定为 `latest`；
  2. 若存在多个 `upcoming` 班期，所有候选必须包含年份信息，依据年月日执行精确比较；缺少年份时拒绝仅凭月份排序；
  3. 若无 `upcoming` 班期，在具有完整日期的非自学（non-self-paced）班期中选取起始时间最新的班期；
  4. 遇到日期缺失年份、日期并列或列表不完整（partial）时，**坚决拒绝根据数字编号猜测最新班期**，直接报错退出。

### 4.3 学员导出对话框与下载流拦截 (`students export`)
- 依据解析出的班期 slug，拼装学员管理页面链接并访问。
- 监控页面 `ENROLLED (<count>)` 状态按钮，等待数字从初始加载状态收敛稳定。
- 定位下载按钮：Maven 学员管理页面的导出按钮为包含特定 SVG 路径（`M8.0625 10.3135L12 14.2499L15.9375 10.3135`）的图标按钮，无内部文本且无 `aria-label`。
- **对话框分步交互**：
  - 点击下载图标按钮，触发弹出 `Export Students` 对话框；
  - 对话框包含 `Enrolled` 与 `Dropped off` 两个复选框；
  - 程序确保 `Enrolled` 被勾选且 `Dropped off` 未被勾选；
  - 读取对话框内标注的 Enrolled 人数，核验其与页面 Enrolled 人数完全吻合；
  - 针对对话框内的 `Export Students` 确认按钮设置下载监听（`expect_download`）并点击触发。

### 4.4 数据质量校验与审计收据
- **CSV 内容校验**：
  - 首行必须不是 HTML 标签或重定向错误页；
  - 必须包含 `email`、`status`、`enrolled_at` 三个必需字段（当前观察到的全量格式为 11 列）；
  - 所有数据行状态必须为 `enrolled`；
  - 邮箱格式必须合法，且全部规范化邮箱去重后无重复；
  - `enrolled_at` 必须为带时区信息的合法时间戳；
  - CSV 数据行数必须严格等于页面展示的 Enrolled 计数。
- **落盘与权限保护**：
  - 导出的 CSV 文件权限设置为 `0600`；若目标路径已存在文件，拒绝覆盖。
  - 在私有 `receipts/` 目录（`0700`）生成收据 JSON 文件（`0600`），记录来源、课程、班期、观察时间、行数、列名、SHA-256 校验和、字节数与文件绝对路径。
  - 更新 `latest.json` 指针指向最新收据。收据与 CLI stdout 中绝不包含任何学员姓名与邮箱。

---

## 5. 安全与错误处理规范

1. **去敏感化错误信息**：捕获的所有底层网络或解析异常，输出至 stderr 时剥离任何私有 Token、Cookie 或开发机敏感信息。
2. **只读保证**：工具仅提供观察与报表导出能力，杜绝提供任何写入接口。
