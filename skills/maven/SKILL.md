---
name: maven
description: Connect to an authenticated Maven browser session via CDP to observe courses, list cohorts, export validated Enrolled student CSV reports, and read Lightning Lesson drafts and aggregate stats without writing.
---

# Maven Agent Skill

本技能为 AI Agent 提供了通过 Chrome DevTools Protocol (CDP) 连接已由人工登录的 Google Chrome 浏览器实例，以只读方式观察 Maven（maven.com）平台课程状态、解析班期（Cohort）排期及安全导出已校验的报名学员（Enrolled）名单 CSV 的标准化操作流程。

> **阶段状态说明**：默认持久 profile 路线已通过独立 agent 的课程发现、最新班期选择和 CSV 导出验收，亦通过关闭重启及临时 headless 运行。`--auth-state` 隔离逻辑通过离线测试，但实机新 context 的认证恢复失败；该选项属于实验路径，不保证可移植登录。

---

## 1. 目标 (Goal)

- 协助课程运营者自动化获取 Maven 平台的课程开设信息与班期进度。
- 在不干扰人类用户当前浏览界面的前提下，安全、有秩序地执行后台工作标签页交互与报表导出。
- 提供经过严格格式校验（必需列、唯一规范化邮箱、带时区时间戳、行数一致性及非 HTML 拦截）的 CSV 文件及只读审计收据。
- 坚持绝对只读原则，严禁进行任何平台数据修改或未授权的外部写入。

---

## 2. 资源与前置条件 (Resources & Prerequisites)

- **系统依赖**：
  - 本地运行环境中已安装 Google Chrome。
  - Python 3.12+ 虚拟环境，并已安装 `maven_skill` 包（提供 `maven-skill` CLI）。
- **会话前置条件**：
  - 人类用户已在终端中执行启动命令：
    ```bash
    maven-skill session open
    ```
  - 人类用户已在弹出的 Chrome 窗口中完成 Maven 账号登录。
- **环境配置**：
  - 默认使用数据目录 `.local`（相对于命令执行时的当前工作目录 cwd）与端口 `9337`。
  - 跨目录调用请设置 `MAVEN_DATA_DIR` 环境变量为绝对路径；自定义端口通过 `MAVEN_CDP_PORT` 注入。
  - **CLI 不会自动读取 `.env` 文件**。

- **参考资料**：
  - [Lightning Lesson 管理界面参考](references/lightning_lessons.md)：导航路径、编辑器字段限制、自动保存与无确认写入等坑点，以及只读安全边界。涉及 Lightning Lesson 的任务先读此文件。

---

## 3. 操作工作流 (Workflow)

AI Agent 在执行 Maven 相关运营任务时，必须严格按以下步骤推进：

### 步骤 1: 验证浏览器连接状态
运行状态检查命令：
```bash
maven-skill session status
```
- **判定逻辑**：
  - 若返回包含 `browser_connected: true`，说明 CDP 调试通信正常，可继续下一步。
  - 若连接失败或超时，**停下来提示用户**：“未检测到活跃的 Maven 浏览器会话，请先执行 `maven-skill session open` 并在弹出的浏览器中完成登录。”
  - **重要提醒**：`status` 仅代表本地调试端口可达，不代表 Maven 平台已完成登录，不可假定凭证有效。

### 步骤 2: 发现与列出课程 (`courses list`)
运行课程发现命令：
```bash
maven-skill courses list
```
- **内部契约**：
  - CLI 从首页账号菜单动态进入 Dashboard，进而访问 Courses 列表，避免硬编码租户或课程路径。
   - 输出页面观察到的课程 URL 与标题列表；支持链接型分页，其他翻页控件报告 partial，必须检查 `completeness`。

### 步骤 3: 提取班期信息并确定目标 (`cohorts list`)
指定课程管理页面 URL，解析班期信息：
```bash
maven-skill cohorts list --course <COURSE_ADMIN_URL>
```
- **内部契约**：
  - 解析所有班期卡片，交叉核验 Student home 与 settings 链接确定唯一的 Cohort slug。
   - `latest` 优先唯一 Upcoming，无需猜测年份；比较多个日期时要求完整年份。导出遇到 partial 列表拒绝推断 latest，可先观察并明确指定实际 slug。

### 步骤 4: 导出已报名单学员 CSV (`students export`)
针对最新班期或指定 slug 班期导出报名学员名单：
```bash
# 导出最新班期
maven-skill students export --course <COURSE_ADMIN_URL> --cohort latest [--output <PATH>]

# 或导出指定班期
maven-skill students export --course <COURSE_ADMIN_URL> --cohort <COHORT_SLUG> [--output <PATH>]
```
- **内部契约与严密校验**：
  - 自动建立独立临时工作标签页，导航至学员管理页面并等待 Enrolled 计数稳定；
  - 点击无文本导出图标按钮打开 `Export Students` 对话框，确保仅勾选 `Enrolled` 并核对人数；
  - 确认导出并拦截保存下载文件；
  - 对 CSV 执行全面校验：必需字段包含 `email,status,enrolled_at`（兼容全量 11 列格式）、全部行状态为 enrolled、规范化邮箱去重无重复、时间戳带时区、总行数与页面计数一致，且拦截重定向 HTML 登录页；
  - 文件设置权限为 `0600`，同名文件拒绝覆盖；
  - 在私有 `receipts/` 目录（`0700`）生成包含 SHA-256、行数、观察时间与路径的收据文件（`0600`），并更新 `latest.json`。
  - 操作完成后自动关闭工作标签页，用户原有标签页保持原貌。

### 步骤 5: 只读查看 Lightning Lesson (`lessons list` / `lessons show` / `lessons stats`)
先读 [Lightning Lesson 管理界面参考](references/lightning_lessons.md)。三个命令只导航和读取，不点击任何可写控件，不输入任何文字：
```bash
# 列出全部 Lightning Lesson（草稿 / 即将开始 / 已结束）
maven-skill lessons list

# 查看单个 lesson 的编辑器字段、字符数与发布阻断项（ID 或管理页 URL 均可）
maven-skill lessons show --lesson <LESSON_ID_OR_ADMIN_URL>

# 已发布 lesson 的聚合统计（单个或全部）
maven-skill lessons stats --lesson <LESSON_ID_OR_ADMIN_URL>
maven-skill lessons stats --all
```
- **内部契约**：
  - 组织路径从账号菜单 → Dashboard 动态发现（与 `courses list` 相同的菜单步骤，菜单按钮先过点击守卫）；传入管理页 URL 时跳过发现。
  - `lessons list` 从列表页 `<details>` 分组（Drafts / Upcoming / Past）读取卡片：ID、标题、状态、管理页 URL，以及卡片上可见的日期时间与报名人数。分组声明数量与解析数量不一致、出现未知分组、游离卡片或翻页控件时报告 `completeness.status=partial`。
  - `lessons show` 先打开 `/<id>`：草稿会跳转到 `/edit`，已发布课程跳转到 overview 标签页，并从页面内嵌的 `__NEXT_DATA__` 中只取聚合字段（报名数、回放观看数、开始时间、时长、是否取消/下架/上架 marketplace、是否关联课程与 promo code）。随后读取编辑器 DOM：标题、日期、开始时间、时区、时长、outcome 标题与字符数、`topic_desc` 字符数（对照页面 `N/M` 计数器或默认上限）、讲师姓名、`N% Complete`、`Review N errors`、带 `data-error="true"` 的卡片、可见的行内错误，以及据此推导的检查项（如缺少事件链接）。折叠卡片的输入框直接从 DOM 读值，不点开。
  - **事件链接只输出布尔值 `event_link_set`**，从不输出链接本身；输出前统一扫描，含邮箱或会议链接时拒绝打印。
  - 编辑器完成后，Maven 页头只剩 Preview 与 Publish，此时 `completion_percent` 为 `null`、`header_reports_complete` 为 `true`。
  - `lessons stats` 只输出聚合数：内嵌数据的 `signup_count`、Signups 标签页标题的 `N signups`（两者可能不同，不做调和）、回放观看数（内嵌数据与 overview 文字交叉核对）。管理界面没有现场到场人数，`live_attendance` 恒为 `null`。
  - **不提供报名日期直方图**：Signups 标签页只在分页表格中、紧挨姓名与邮箱显示粗粒度相对时间（如 “a month ago”），精确时间戳只能来自未公开 API；按仓库规则不逆向私有接口，因此 `signup_date_histogram.available=false` 并附原因。
  - 所有 lesson 页面通过 `ReadOnlyPage` 访问：只有导航与登记过的只读脚本，没有 click / fill / type / keyboard / locator 接口；点击守卫拒绝 Publish、Create a Lightning Lesson、Create a Zoom meeting、Delete instructor、Save 等标签及含写入动词的控件。工作标签页在 `finally` 中关闭。

### 步骤 6: 隔离上下文模式（可选）
如需通过既有认证状态快照在独立上下文中执行：
```bash
maven-skill --auth-state .local/auth-state.json courses list
```
- 全局选项 `--auth-state` 必须放在子命令前。该模式在已有浏览器中开辟独立 Context 执行，完成即销毁临时 Context。
- 实测 Maven 会清除传入新 context 的认证 cookie，即使刚执行 `session save`。失败时明确报告 snapshot 认证未通过，不把 profile 验收冒充 snapshot 成功，不把匿名 context 的状态写回有效快照。默认用持久 profile 保存的登录态；若用户允许该路线，省略 `--auth-state` 重试。
- 用户屏幕共享时，不打开可见窗口。可用用户授权的本地临时 wrapper 启动 headless Chrome，复用同一 profile 和 CDP；不要永久修改 CLI 默认值。

---

## 4. 输出规范 (Output)

向用户交付任务结果时，输出应遵循以下规范：
1. **当前会话状态**：明确说明 CDP 端口与浏览器连接情况。
2. **业务操作摘要**：列出操作的课程名称/URL 及班期标识；Lightning Lesson 任务列出 lesson ID、状态与发布阻断项。
3. **统计数据与产物指标**：报告已导出的 Enrolled 学员人数、CSV 文件相对路径、文件大小及 SHA-256 校验和。
4. **零 PII 原则**：CLI stdout 与回复中**严禁打印任何学员的真实姓名或邮箱地址**。

---

## 5. 验收标准 (Acceptance Criteria)

- [x] 会话状态检查能够正确反映 CDP 连通性。
- [x] 课程列表动态定位并输出观察到的课程，同时声明完整性。
- [x] 班期列表解析观察到的卡片；明确 Upcoming 时可确定 latest，否则不猜测。
- [x] 学员导出命令能够完成对话框交互、下载 Enrolled CSV 并通过全部数据有效性校验。
- [x] 导出产物生成符合规范的 SHA-256 审计收据，权限控制严格（目录 `0700`，文件 `0600`）。
- [x] 业务命令执行过程中，用户在浏览器中原有的标签页不受干扰。
- [x] `lessons list` 动态定位 Lightning Lessons 列表，输出 ID、标题、状态与可见的日期和报名数，并声明完整性。
- [x] `lessons show` 读取草稿与已发布 lesson 的字段、字符数对照上限、完成度与可见发布错误；事件链接只输出布尔值。
- [x] `lessons stats` 只输出聚合报名数与回放观看数；报名日期直方图因需要未公开 API 而明确标记不可用。
- [x] lessons 命令不点击、不输入；点击守卫与只读页面门面有单元测试覆盖。
- [x] 138 项离线单元测试与隐私检查全部通过。

---

## 6. 安全红线与业务边界 (Safety & Boundaries)

- **绝对只读红线**：
  - 严禁修改课程大纲、价格、班期排期或学生状态。
  - 严禁自动向学生发送邀请邮件、私信或系统通知。
  - 严禁调用任何形式的外部资金转账、分润结算或 Ledger 写入接口。
  - **任何业务写入操作必须先停下，向人类用户陈述意图并获得独立显式授权**。
- **隐私保护**：
  - 严禁在长久公共文档、公开日志或交互回复中打印真实学员信息。
  - 所有公开文档与测试用例中一律采用虚拟示例数据（fake examples）。
- **去密错误提示**：
  - 遇到网络异常或页面结构变化时，输出脱敏的错误信息，杜绝暴露 Cookie 或敏感凭据。

---

## 7. 技能安装与配置说明

在将本技能集成至其他 AI Agent 工作区（如 Codex、Claude Code、Cursor 或 OpenCode）时：
1. 提交本仓库的公开 GitHub URL（`https://github.com/grapeot/maven-skill`）。
2. 在目标工作区仅将 `skills/maven/SKILL.md` 注册为唯一根技能。
3. 宿主环境特有的账号别名、专用数据目录绝对路径或个性化环境变量，请完全在宿主自己的私有 overlay（如 `rules/skills/maven.md`）中维护，严禁直接污染公共技能包。
