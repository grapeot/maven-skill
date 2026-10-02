---
name: maven
description: Connect to an authenticated Maven browser session via CDP to observe course/cohort pages and download CSV reports.
---

# Maven Agent Skill

本技能为 AI Agent 提供了通过 Chrome DevTools Protocol (CDP) 连接已由人工登录的 Google Chrome 浏览器实例，以只读方式观察 Maven（maven.com）平台课程状态、Cohort 列表及安全下载报表 CSV 的标准化操作流程。

> **阶段状态说明**：Session 基础设施、登录后课程/cohort 页面观察及单一 cohort 的 enrolled CSV 下载已完成实机验证。业务操作目前由 Playwright CDP 完成，尚无专用列表/下载 CLI；其他页面布局和分页仍需现场观察。

---

## 1. 目标 (Goal)

- 协助人类操作者观察并提取 Maven 平台的课程运营数据与 Cohort 进度。
- 在不干扰人类用户正在浏览页面的前提下，安全、有秩序地执行页面跳转与快照检查。
- 实现结构化的数据提取报告，具备明确的分页完整性标注与下载有效性验证。

---

## 2. 资源与前置条件 (Resources & Prerequisites)

- **系统依赖**：
  - 本地运行环境中已安装 Google Chrome。
  - Python 3.12+ 虚拟环境，并已安装 `maven_skill` 包（提供 `maven-skill` CLI）。
- **会话前置条件**：
  - 人类用户已在终端中执行过启动命令：
    ```bash
    maven-skill session open
    ```
  - 人类用户已在弹出的 Chrome 窗口中成功登录 Maven 平台账号。
- **环境配置**：
  - 默认使用数据目录 `.local` 与端口 `9337`。若有自定义需求，通过 shell 环境变量 `MAVEN_DATA_DIR` 和 `MAVEN_CDP_PORT` 注入。

---

## 3. 操作工作流 (Workflow)

AI Agent 在执行 Maven 相关任务时，必须严格按以下顺序推进：

### 步骤 1: 验证浏览器连接状态
运行状态检查命令：
```bash
maven-skill session status
```
- **判定逻辑**：
   - 若返回包含 `browser_connected: true`，说明 CDP 通信正常，继续下一步。
  - 若连接失败或超时，**停下来提示用户**：“未检测到活跃的 Maven 浏览器会话，请先执行 `maven-skill session open` 并在弹出的浏览器中完成登录。”
  - **重要原则**：状态可连接不等于 Maven 已登录，绝不能假定已就绪。

### 步骤 2: 观察当前页面状态
在执行任何页面跳转前，必须先观察用户当前的页面停留状态：
```bash
maven-skill page snapshot
```
- **判定逻辑**：
  - 检查快照文本，确认当前活跃页面是否为 Maven 页面，以及用户是否正停留在特定表单或编辑页。
  - **严禁**未经观察直接盲目覆盖用户正在填写的页面或重载窗口。

### 步骤 3: 目标页面定向导航
确认可安全导航后，驱动浏览器访问目标管理视图：
```bash
maven-skill page goto https://maven.com/
```

具体管理页 URL 必须来自当前页面的真实链接，不猜测 Dashboard 路径。CLI 只提供观察和跳转；更复杂的点击与等待可使用 Playwright `chromium.connect_over_cdp("http://127.0.0.1:9337")` 接入同一浏览器，完成后仅断开客户端，不关闭用户窗口。

### 步骤 4: 观察与提取 Cohort 信息（*后续目标*）
- 观察页面呈现的 Cohort 列表。
- **分页与完整性声明**：
  - 若页面包含分页（Pagination）或滚动加载，必须逐页观察并核验记录总数。
  - 在最终报告中，**必须明确说明数据的完整性状态**（例如：“共观察到 3 个分页，已完整提取 42 条 Cohort 记录”或“仅提取当前第一页显示的部分”）。
  - **只报告观察到的事实**，绝不推测或补全未直接在页面上呈现的信息。

### 步骤 5: 报表 CSV 下载与有效性核验（*后续目标*）
- 触发报表导出下载。
- **文件有效性校验**：
  - 下载文件仅保存在本地私有安全目录中。
  - 下载完成后，**必须检查文件内容本身**，确认其前几行符合合法的 CSV 文本格式。
   - **特别注意**：严禁仅依据文件扩展名判断；若会话过期，服务端可能返回一个扩展名为 `.csv` 但实际内容为 HTML 登录页重定向文本的虚假文件，必须通过内容检查将其识别并拦截。

已验证的页面入口是账号菜单中的 Dashboard → Courses → 课程 → Students。账号菜单和课程链接随账号变化，以页面实际 href 为准，不把某个账号的路径写成通用固定值。

Students 页顶部的下载入口是一个无文本的下载图标按钮，不能用 `get_by_role("button", name="Export")` 直接定位。第一次点击打开 `Export Students` dialog，并不开始下载。对话框允许选择 Dropped off / Enrolled；实测默认只勾选 Enrolled。核对勾选和数量后，围绕对话框内的 `Export Students` 按钮使用 `page.expect_download()`，再 `download.save_as()` 保存到私有目录。

实测 CSV 表头：`full_name,preferred_name,email,status,company,job_title,linkedin_url,twitter_username,course_join_question,enrolled_at,source`。后续运行仍要检查表头、规范化邮箱唯一性、状态、报名日期与页面人数是否一致；不得仅因一次验证成功而跳过检查。

---

## 4. 输出规范 (Output)

向用户交付任务结果时，输出应包含以下结构：
1. **当前会话状态**：明确说明 CDP 端口与浏览器连接情况。
2. **页面观察摘要**：简明列出当前所在的 Maven URL 与页面主标题。
3. **数据提取清单**：以 Markdown 表格或结构化列表列出观察到的 Cohort/学员信息，并带有清晰的分页完整性标注。
4. **下载产物校验**：若涉及下载，报告本地文件存储路径（必须为私有相对路径）、文件大小及 CSV 头格式校验结论。

---

## 5. 验收标准 (Acceptance Criteria)

- [x] 会话状态检查命令能够正确返回 CDP 连通性。
- [x] 页面快照能够如实反映当前浏览器视口的文本，无异常报错。
- [x] 用户登录后可观察课程列表、全部可见 cohort 和最新 cohort 学生计数；跨重启登录有效性待测。
- [ ] （后续目标）若存在分页，能准确上报提取范围与完整性。
- [x] 单一 cohort 的 enrolled CSV 已下载并验证字段、行数、状态和报名日期。

---

## 6. 安全红线与业务边界 (Safety & Boundaries)

- **绝对只读红线**：
  - 严禁修改课程大纲、价格、班期排期或学生状态。
  - 严禁自动向学生发送邀请邮件、私信或系统通知。
  - 严禁调用任何形式的外部资金转账、分润结算或 Ledger 写入接口。
  - **任何业务写入操作必须先停下，向人类用户陈述意图并获得独立显式授权**。
- **隐私保护**：
  - 页面观察快照中可能包含真实学员的姓名、邮箱等个人敏感信息。
  - Agent 在记录思考过程、总结回复或生成文档时，必须避免打印或暴露真实个人信息。
- **示例数据守则**：
  - 本技能包及公开仓库中涉及的任何示例，一律采用虚拟假数据（fake examples，如 `fake_cohort_2026_q1`、`student_placeholder_01`）。

---

## 7. 技能安装与配置说明

若需将本技能集成至其他 AI Agent 工作区（如 Codex、Claude Code、Cursor 或 OpenCode）：
1. 将本代码仓库的 GitHub URL 提供给 Agent。
2. 指引 Agent 查阅目标工作区的 `AGENTS.md` / `CLAUDE.md` 及技能索引（例如 `rules/skills/INDEX.md`），将唯一根技能挂载为 `skills/maven/SKILL.md`。
3. 宿主环境特有的账号别名、专用数据目录绝对路径或个性化环境变量，请完全在宿主自己的私有 overlay（如 `rules/skills/maven.md`）中维护，不得直接污染或硬编码至公共技能包中。
