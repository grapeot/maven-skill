---
name: maven
description: Connect to an authenticated Maven browser session via CDP to observe courses, list cohorts, export validated Enrolled student CSV reports, read Lightning Lesson drafts and aggregate stats, and read course reviews (public landing-page reviews and per-cohort post-course survey ratings) without writing.
---

# Maven Agent Skill

本技能是面向 Maven（maven.com）平台的只读工具，采用「浏览器优先、人工登录、Agent 观察」架构，通过 Chrome DevTools Protocol (CDP) 连接已登录的 Chrome 实例，执行课程与班期观察、Lightning Lesson 查看、课程评价读取及已校验的报名学员名单导出。

> **阶段状态说明**：默认持久 profile 路线已验证（支持课程发现、最新班期选择、CSV 导出及重启与临时 headless 运行）。`--auth-state` 隔离逻辑属于实验路径，离线测试通过但在实机新 context 中认证恢复失败，不保证可移植登录。

---

## 1. 目标

- 自动化以只读方式获取 Maven 课程开设信息、班期排期及 Lightning Lesson 状态与统计。
- 在不干扰用户当前浏览界面的前提下，安全执行后台工作标签页交互与学员名单 CSV 导出。
- 坚持绝对只读原则，提供严格校验与 SHA-256 审计收据的产物，严禁任何平台修改或未授权写入。

---

## 2. 前置：会话与登录（必须先做）

任何业务操作前，必须完成登录与会话连通检查这一项串行前置闸：

1. **人工登录是业务前置**：需要用户已登录 Maven（或持久 profile 中已有有效登录态）。若浏览器尚未启动，由人类用户在终端执行：
   ```bash
   maven-skill session open
   ```
   并在弹出的 Chrome 窗口中完成登录。**若浏览器已运行但未登录或登录失效，同样需要人工登录**；先读 [会话与登录配置参考](references/session.md)，尤其用户屏幕共享时不得打开可见窗口。
2. **连通性检查**：Agent 执行：
   ```bash
   maven-skill session status
   ```
   - 返回包含 `browser_connected: true` 时方可继续；连接失败或超时则**停下来提示用户**：“未检测到活跃的 Maven 浏览器会话，请先执行 `maven-skill session open` 并在弹出的浏览器中完成登录。”
   - **重要提示**：`status` 仅代表本地 CDP 调试端口可达，**不代表 Maven 已登录**。业务命令若报告未认证（跳转登录页、找不到账号菜单），停止并提示用户登录。

环境变量、数据目录、端口、`--auth-state` 与 headless 运行等细节见 [会话与登录配置参考](references/session.md)。

---

## 3. 任务路由（Runbook）

会话连通后，各只读任务彼此独立，按需执行对应命令即可：

| 任务 | 命令 | 先读的 reference |
|---|---|---|
| 查课程列表 | `maven-skill courses list` | [references/courses_cohorts.md](references/courses_cohorts.md) |
| 查班期 / 确定 latest | `maven-skill cohorts list --course <COURSE_ADMIN_URL>` | [references/courses_cohorts.md](references/courses_cohorts.md) |
| 导出 Enrolled 学员 CSV | `maven-skill students export --course <COURSE_ADMIN_URL> --cohort latest\|<COHORT_SLUG> [--output <PATH>]` | [references/students_export.md](references/students_export.md) |
| 只读查看 Lightning Lesson | `maven-skill lessons list`<br>`maven-skill lessons show --lesson <ID_OR_URL>`<br>`maven-skill lessons stats --all`（或 `--lesson <ID_OR_URL>`） | [references/lightning_lessons.md](references/lightning_lessons.md) |
| 读课程评价（公开评价 / 班期问卷评分） | `maven-skill reviews list --course <PUBLIC_COURSE_URL\|COURSE_ADMIN_URL>`<br>`maven-skill reviews surveys --course <COURSE_ADMIN_URL> [--download [--cohort <LABEL\|N>] [--output-dir <DIR>]]` | [references/reviews.md](references/reviews.md) |
| 只读核对折扣码（promo code） | 无 CLI，浏览器只读观察 | [references/promo_codes.md](references/promo_codes.md) |
| 生成带折扣的分享链接 | 无 CLI，按格式拼接后用未登录浏览器验收 | [references/promo_codes.md](references/promo_codes.md)「折扣分享链接」 |
| 会话与登录配置 | `maven-skill session open\|status\|save\|close` | [references/session.md](references/session.md) |

命令细节见对应 reference；只有第 2 节的会话连通检查是串行前置，其余只读任务按需单独执行，不必按顺序走。

**Maven 业务写入的通用规则**（CLI 本身只读；折扣码与 Lightning Lesson 编辑器等写入路径见对应 reference，且都需先获授权）：

- **授权**：创建、暂停、删除折扣码是业务写入，CLI 不实现，默认由人类操作，Agent 仅在用户对**具体动作**单独显式授权后才可协助；参考文档与操作步骤本身不构成授权（详见 [references/promo_codes.md](references/promo_codes.md) 与第 5 节）。
- **Code 字符集**：Maven 折扣码只接受字母、数字和连字符 `-`，**不接受下划线**。构造代码时先做 `^[A-Za-z0-9-]+$` 自检。含 `_` 的代码会被客户端校验拒绝；已观察到的一种形态是既不发请求也无弹窗，表现为「点了没反应」，因此不能靠界面反馈猜测成败。
- **写后必须读回验证**：任何写入完成后，不能以「点击了、无报错、界面有反应」当成功。必须重新加载页面、读回权威视图（表格/详情），确认目标变更真的存在且符合预期，才算完成。这是所有写入任务的通则，不限于折扣码。

---

## 4. 输出与隐私

向用户交付任务结果时，输出应遵循以下规范：
1. **当前会话状态**：说明 CDP 端口与浏览器连接情况。
2. **业务操作摘要**：列出操作的课程 URL 及班期 slug；Lightning Lesson 任务列出 lesson ID、状态与发布阻断项。
3. **统计数据与产物指标**：报告 Enrolled 学员人数、CSV 文件相对路径、文件大小及 SHA-256 校验和。
4. **零 PII 原则**：CLI stdout 与回复中**严禁打印任何学员的真实姓名或邮箱地址**。唯一例外是 `reviews list`：它原样输出公开落地页上已经展示的评价者显示名与头衔；问卷 CSV 中的姓名、邮箱与私下留言仍只留在私有目录。

---

## 5. 安全红线与业务边界

- **绝对只读红线**：
  - 严禁修改课程大纲、价格、班期排期或学生状态。
  - 严禁自动向学生发送邀请邮件、私信或系统通知。
  - 严禁调用任何形式的外部资金转账、分润结算或 Ledger 写入接口。
- **折扣码边界**：
  - 创建、暂停或删除折扣码（promo code）都是业务写入，CLI 不实现；默认由人类操作，Agent 仅可在用户对**具体动作**单独显式授权后协助；参考文档与操作步骤本身不构成授权。
  - 任何业务写入操作必须先停下，向人类用户陈述意图并获得独立显式授权。
- **只读交互约束**：
  - `lessons` 系列命令只导航和读取，不点击任何可写控件，不输入任何文字；事件链接只输出布尔值。
  - `reviews` 系列命令不回复、不发布、不隐藏任何评价，只点击 `Show more reviews` 与（`--download` 时）班期问卷的 `N responses` 下载按钮。
- **隐私与脱敏保护**：
  - 严禁在公开文档、日志或交互回复中打印真实学员信息；所有公开文档与测试一律用虚拟示例（fake examples）。
  - 遇到异常时输出脱敏的错误信息，杜绝暴露 Cookie 或敏感凭据。

---

## 6. 技能安装与配置说明

在将本技能集成至其他 AI Agent 工作区（如 Codex、Claude Code、Cursor 或 OpenCode）时：
1. 提交本仓库的公开 GitHub URL（`https://github.com/grapeot/maven-skill`）。
2. 在目标工作区仅将 `skills/maven/SKILL.md` 注册为唯一根技能。
3. 宿主环境特有的账号别名、专用数据目录绝对路径或个性化环境变量，请完全在宿主自己的私有 overlay（如 `rules/skills/maven.md`）中维护，严禁直接污染公共技能包。
