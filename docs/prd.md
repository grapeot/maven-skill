# 产品需求文档 (PRD): Maven Skill

## 1. 背景与目标

### 1.1 业务背景
课程运营者需要定期查看 Maven（maven.com）平台的课程开设状态、各班期（Cohort）排期与学员报名情况，并获取报表 CSV。本项目基于真实系统级 Google Chrome 与 Playwright 建立浏览器优先的自动化工具与 Agent 技能包，规避官方 API 范围未知及私有接口频繁变更的风险。

### 1.2 核心目标
1. **可靠的浏览器会话底座**：驱动 Google Chrome，由人类完成初始认证，将登录凭证保存在本地独立 Profile 中；Agent 通过本地 CDP 回环端口介入。
2. **动态路由与免硬编码**：从 Maven 首页账号菜单自动路由至 Dashboard 与 Courses，避免在代码或配置中硬编码租户和课程路径。
3. **班期结构化提取与智能判定**：交叉核验页面链接提取 Cohort 标识（slug），依据严格的日期规范判定最新班期（`latest`），杜绝不可靠的数字序号推测。
4. **高质量报表导出与校验**：在学员管理界面精准筛选 Enrolled 学员并触发下载；对 CSV 执行严密格式校验（必需列、唯一规范化邮箱、带时区时间戳、行数一致性及非 HTML 检测）；输出带 SHA-256 校验和的审计收据（receipt）。
5. **用户交互低侵入性**：业务命令在已有浏览器中开辟新工作标签页，执行完毕即刻关闭，保持用户原有浏览标签页原封不动；支持基于 `--auth-state` 建立临时上下文执行。
6. **零 PII 泄露输出**：业务命令 stdout 仅输出聚合状态与统计，杜绝打印学员个人身份信息（PII）。

### 1.3 非目标
- **不逆向私有 API**：不直接调用或逆向 Maven 内部 HTTP 接口。
- **不执行平台写操作**：严禁修改课程、变更排期、更改学员状态或发送邀请通知。
- **不内嵌外部业务规则**：不包含资金清算、分润计算或 Ledger 账本写入逻辑。
- **不尝试自动绕过登录验证**：登录交由人类操作者在图形界面完成。

---

## 2. 用户角色与典型工作流程

### 2.1 角色定义
- **人类操作者**：负责初次打开会话、在弹出的 Chrome 窗口中完成账号登录、在会话失效时重新认证。
- **AI Agent**：负责在用户登录后，调用 CLI 业务命令执行课程列出、班期分析及学员数据导出。

### 2.2 核心工作流程
```
[人类操作者]
   │
   ├─► 1. 运行: maven-skill session open
   │      └─► 弹出独立 Chrome 窗口
   │
   ├─► 2. 人工在窗口中登录 Maven 账号
   │      └─► 凭据自动持久化至 .local/browser-profile
   ▼
[AI Agent]
   │
   ├─► 3. 运行: maven-skill session status
   │      └─► 确认 CDP 端口可达
   │
   ├─► 4. 运行: maven-skill courses list
   │      └─► 动态发现已发布课程列表与管理 URL
   │
   ├─► 5. 运行: maven-skill cohorts list --course <COURSE_URL>
   │      └─► 提取所有班期卡片并确定 latest 候选
   │
   └─► 6. 运行: maven-skill students export --course <COURSE_URL> --cohort latest
          └─► 过滤 Enrolled、下载 CSV、校验数据、生成审计收据
```

---

## 3. 功能需求规格

### 3.1 会话与页面管理
- **`session open [--url URL]`**：唤起或复用 Chrome 实例，绑定 `.local/browser-profile` 与指定端口，复用时不覆盖用户当前页面。
- **`session status`**：检测 CDP 调试端口连通性。该命令仅代表端口可达，不代表平台已登录。
- **`session save`**：将当前会话的 Cookies、localStorage 及 IndexedDB 导出至 `.local/auth-state.json`（权限 `0600`）。
- **`session close`**：先保存认证状态快照，随后关闭 Chrome 浏览器进程。
- **`page snapshot`**：读取最后一个 Maven 标签页的可见文本与主要控件信息。
- **`page goto <URL>`**：驱动最后一个 Maven 标签页导航至指定链接（仅限 Maven 域名 HTTPS）。

### 3.2 业务操作命令 (v0.1)
- **`courses list`**：
  - 从 Maven 首页查找账号菜单按钮，点击并打开菜单；
  - 提取 Dashboard 链接并跳转，定位 Courses 管理页；
  - 遍历翻页并对课程链接进行去重，输出结构化课程列表。
- **`cohorts list --course <COURSE_URL>`**：
  - 进入课程概览页，解析各个班期的卡片；
  - 提取 Student home 链接及设置链接中的 `cohort` 参数，双向一致核对后提取唯一 slug；
  - 判定 `latest`：优先选取唯一的 Upcoming 班期；多个班期需具备完整年份进行日期比较；若日期缺失年份、存在并列日期或列表不完整，拒绝通过数字推导 `latest`。
- **`students export --course <COURSE_URL> --cohort <latest|SLUG> [--output PATH]`**：
  - 进入学员列表页面，等待并读取页面显示的 Enrolled 人数；
  - 点击无文本下载图标按钮，弹出 Export Students 对话框；
  - 确保仅勾选 Enrolled 状态，核对对话框人数与页面 Enrolled 人数一致；
  - 点击对话框内的确认导出按钮，监听下载事件；
  - 保存并校验 CSV 内容（必需包含 `email,status,enrolled_at`，全部状态为 enrolled，规范化邮箱唯一，日期带时区，行数严格匹配页面计数，严禁 HTML）；
  - CSV 写入权限 `0600`，同名文件拒绝覆盖；
  - 在 `.local/receipts/` 生成收据 JSON（`0600`），记录 SHA-256、行数、观察时间及绝对路径，更新 `latest.json` 指针。

### 3.3 全局参数与环境隔离
- `--data-dir` / `MAVEN_DATA_DIR`：数据存放根目录，默认 `.local`。相对路径相对于执行命令时的 cwd。
- `--port` / `MAVEN_CDP_PORT`：CDP 调试端口，默认 `9337`。
- `--auth-state FILE`：全局参数，写在子命令前。在已有浏览器中开辟独立 context 载入存储状态执行，执行结束仅关闭临时 context。

---

## 4. 安全、隐私与权限要求

1. **网络与接口安全**：CDP 端口仅监听 `127.0.0.1` 本地回环地址，严禁暴露至公网。
2. **文件权限控制**：数据目录与 receipts 目录权限设为 `0700`，认证快照、导出 CSV 与收据文件权限设为 `0600`。
3. **版本控制防泄露**：`.local/`、日志文件、下载目录及 `.env` 必须严格包含在 `.gitignore` 中。
4. **输出去敏化**：业务命令 stdout 绝不打印学员姓名与邮箱。异常处理输出脱敏错误信息，不泄露凭据或私密路径。
5. **绝对只读红线**：严禁执行任何变更课程排期、编辑学生信息、发送邀请或外部记账操作。

---

## 5. 验收标准

### 5.1 已实现与验证项 (v0.1)
- [x] 会话管理与 CDP 连接复用（端口探测、进程守护与 profile 校验）。
- [x] 动态路径发现：首页账号菜单 → Dashboard → Courses。
- [x] 班期卡片解析、slug 双向核验与安全的 `latest` 选期逻辑。
- [x] 学员页面导出对话框交互、Enrolled 精确筛选与下载流拦截。
- [x] 导出的 CSV 全面数据质量校验（表头、行长、Enrolled 状态、规范化邮箱唯一性、带时区时间戳及行数一致性）。
- [x] 审计收据生成（SHA-256、时间戳、文件指针与 `0600`/`0700` 权限管控）。
- [x] 138 项自动化离线单元测试与隐私检查全部通过（含 Lightning Lesson 只读命令）。
- [x] 实机环境下默认 profile 模式的课程列表、班期解析与学员 CSV 导出实测通过，原有用户标签页完好保留。

### 5.2 待验证演进项
- [ ] 基于 `--auth-state` 的新 context 登录恢复：实测失败，仍属实验路径，不保证认证可移植。
- [x] 跨 Chrome 重启后的 profile 登录复用，以及独立 agent 的 headless CSV 导出对照验收。
