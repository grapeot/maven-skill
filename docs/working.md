# Working Notes: Maven Skill

本文档用于跟踪 `maven_skill` 项目的开发进度、架构决策与待实测验证项。

---

## 2026-10-05（续）: Promo Code 真实创建验证与坑点沉淀

### 1. 背景
- 此前 `promo_codes.md` 只记录了界面观察，「点击后行为」标注为未验证。本轮经用户显式授权，在某课程上真实创建了一个 $200 折扣码并刷新验证。

### 2. 关键坑点（已写入 `references/promo_codes.md`）
1. **Code 只接受字母、数字、连字符**：含下划线的代码（最初目标含 `_`）会被客户端校验拒绝，内联提示 `Promo code can only contain letters, numbers, and hyphens`，**且不发出任何 HTTP 请求**。表格不会新增行，表现为「点了没反应」，容易误判为脚本问题。改用连字符后创建成功。
2. **创建失败无弹窗、无 toast**：错误只是 Code 字段附近的一行内联文字，必须主动读取，不能靠「有没有弹窗」判断。
3. **受控输入**：`code` / `amount_off` / `percent_off` 是 React 受控输入，必须经原生 setter + 派发 `input`/`change` 事件写入，否则组件状态为空、提交无效。
4. **金额格式**：`amount_off` 直接填整数（`200` → `$200`），不需要 `$`；表格用 `$` 前缀 + 千分位显示。
5. **验收必须刷新复验**：点击后表格出现新行还不算数，`reload` 后该行仍在（行数 +1）才判定成功。
6. **Redemptions 初值是 `-`**，不是 `0`。

### 3. 实现说明
- 创建是浏览器写入，CLI 未实现、本轮也不新增写命令。验证用的私有脚本与网络/表单诊断留在 `.local/coupon_probe/`，不进入公开仓库；公开文档里的代码名一律用虚构占位符。
- 本轮为文档更新（`references/promo_codes.md`、本文件），CLI 与测试不变。

---

## 2026-10-05（续）: 主 Skill 重构为任务路由 runbook

### 1. 今日完成工作
- 把 `SKILL.md` 从「步骤 1 → 步骤 7」的线性管线改成「前置会话闸 + 任务路由表 + 各任务一个 reference」的 runbook，196 行降到约 95 行。由 Antigravity CLI（`gemini-3.8-flash-high`）起草，主线程审核。
- 细节下沉：新增 `references/session.md`（会话命令语义、环境变量、`--auth-state` 隔离上下文、headless）、`references/students_export.md`（导出命令、标签页生命周期、CSV 校验、收据）、`references/courses_cohorts.md`（课程/班期发现契约、`latest` 三条选期路径）。
- `references/promo_codes.md` 未改；`references/lightning_lessons.md` 仅更新根 Skill 交叉引用，并按 review 补齐 CLI 输出语义（partial、`completion_percent=null`、`live_attendance=null`、直方图不可用）与只读防护实现小节。
- 按 review 修复：恢复快照失败后切 profile 的用户允许条件、恢复屏幕共享不得开可见窗口的硬约束、明确人工登录是业务前置、路由行标明折扣码写入例外。
- 保留事实：会话连通是唯一串行前置闸；零 PII；绝对只读红线；折扣码写入边界。移除误导性的“点击写入”步骤编号。

### 2. 设计动机
- 线性步骤诱导“按流程往下点”，此前已在 review 中造成“只读 skill 里出现点击写入步骤”的高严重度冲突。
- 除会话连通外各任务彼此独立，任务来了通常是单点（导某班期名单、查某折扣码），不需要走完整管线。

### 3. 本轮仅文档变更，CLI 行为与测试数量（138 项）不变。

---

## 2026-10-05: Promo Code 管理界面文档

### 1. 今日完成工作
- 新增 `skills/maven/references/promo_codes.md`，并在 `SKILL.md`（新增步骤 6）与 `README.md`（第 6 节）链接。
- 内容为对课程 Settings 页 Payments 组内 Promo codes 区块的人工观察：入口路径、常驻内联创建表单字段（`code` / `amount_off` / `percent_off` 与 `OR` 规则）、提交按钮文本、已有码表格列与 Actions 图标、写入授权边界，并交叉引用 Maven 帮助中心《Discount code strategies》的规则（课程级、可暂停/删除、不支持 100% off、分成基于实付价）。
- 本轮仅文档变更，CLI 行为与测试数量（138 项）不变。

### 2. 观察到的坑点
1. 创建表单是常驻内联 `<form>` 而非弹窗，只要课程已接 Stripe 并设价即可见。
2. 区块标题 `Create a promo code` 与提交按钮 `Create promo code` 文本相近，定位易混淆。
3. `code` / `amount_off` / `percent_off` 在 DOM 上均无 `required`，浏览器不会阻止空提交；错误文案与校验位置未测。
4. Actions 列三个图标按钮无文字、无 `aria-label`、无 `title`，真实 hover 无 tooltip；中间枚 SVG 路径在多行间不稳定，无法按名称或路径区分复制链接 / 暂停 / 删除。
5. `Direct payment link` 区块是班期 join 链接（`/<cohort>/join?seats=1`），不含 promo 参数，不能用来拼折扣分享链接。

### 3. 未验证假设（刻意未点击写入）
- 点击 `Create promo code` 后是否有二次确认、新码是否立即对学生可见，均未点击验证；本文档不把「无确认、立即生效」当已知事实写进公开文档。
- 金额/百分比输入框接受的字符串格式未测；只有表格**显示**格式（`$100` / `25%`）经实测。
- 新建行的 Redemptions 初值未测；已知空值显示为 `-`，未见 `0`。

### 4. 写入边界
- 本轮未执行任何写入：仅导航与读取，未填字段、未点提交按钮。探测脚本全程只读，工作标签页在 `finally` 中关闭。
- 文档明确：创建、暂停、删除折扣码属业务写入，CLI 不实现，默认由人类操作，Agent 仅在人类对具体动作单独显式授权后可协助；参考文档与操作步骤本身不构成授权。

---

## 2026-10-03（续）: Lightning Lesson 只读命令

### 1. 完成工作
- 新增 `lessons list`、`lessons show --lesson <ID_OR_ADMIN_URL>`、`lessons stats (--lesson ... | --all)`。纯解析函数在 `parse.py`，浏览器编排与只读脚本在 `ops.py`，CLI 接线在 `cli.py`；沿用 `run_business` / `work_page` 工作标签页生命周期。
- 只读护栏：lesson 页面全部经 `ReadOnlyPage` 访问（只有导航与登记脚本，无 click / fill / type / keyboard / locator）；`assert_click_allowed` 拒绝写入类控件标签，并接入共享的账号菜单步骤；输出前 `assert_public_output` 拒绝邮箱与会议链接。
- 测试由 38 项增至 138 项（含参数化），新增 `tests/test_lessons.py`，全部使用手写虚拟数据。
- 文档：`SKILL.md` 步骤 5 与验收标准、`README.md`、`references/lightning_lessons.md`（读取契约）、`docs/test.md`、`docs/prd.md`、`AGENTS.md` 测试数与命令范围。

### 2. 实机只读验证（只记录聚合结论）
- [x] `lessons list`：三个分组的声明数与解析数一致，`completeness=complete`；连续 4 次运行稳定。
- [x] `lessons show`：一个草稿与一个已结束 lesson；日期、开始时间、时区、时长、计数器、链接布尔值、讲师错误标记与 `Review N errors` 一致；已发布 lesson 的回放观看数在内嵌数据与 overview 文字间一致。
- [x] `lessons stats --lesson` 与 `--all`：只输出聚合数；所有输出 grep 无邮箱与会议链接。
- [x] 每次运行前后浏览器标签页集合一致，未留下工作标签页；未点击、未输入、未修改任何 lesson。

### 3. 问题与解决
1. 已发布 lesson 的编辑器页头没有 `N% Complete`，最初的就绪条件因此超时；改为等待标题输入框、讲师区块与开始时间显示值。
2. Past 分组默认折叠，`innerText` 为空；列表与计数读取改用 `textContent`。
3. 回放观看数的数字与说明文字不在同一叶子节点，改为匹配短文本容器。
4. 完成的草稿页头只剩 Preview 与 Publish，无百分比；输出 `header_reports_complete=true` 而不臆造 100%。
5. 报名日期直方图跳过：精确时间只能来自未公开 API，Signups 标签页只有与 PII 同处的相对时间。
6. 一次运行中账号菜单未及时展开导致发现失败，重跑即通过；属于共享步骤的偶发时序问题，未改动其等待逻辑。

---

## 2026-10-03: Lightning Lesson 管理界面观察记录

### 1. 今日完成工作
- 新增 `skills/maven/references/lightning_lessons.md`，并从 `SKILL.md` 与 `README.md` 链接。内容为对 Lightning Lesson 管理界面的人工观察：导航路径（列表、编辑器、已发布课程的 overview / signups / settings 标签页）、编辑器字段契约与字符上限、Maven 帮助中心的推广节奏与到场率经验值。
- 本轮仅为文档变更，CLI 行为与测试数量不变。

### 2. 观察到的坑点
1. 点击 “Create a Lightning Lesson” 立即创建草稿，无确认。
2. 编辑器没有保存按钮，字段自动保存；输入即写入，属于需要授权的业务写操作。
3. 新草稿只有一条 learning outcome，折叠的 outcome 卡片需点开才会显示输入框。
4. 新草稿自动加入与组织 expert profile 同步的讲师条目，可能是机构且必填 bio 为空；“Delete instructor” 无确认即生效。
5. 事件链接是硬性发布阻断项；唯一的链接选项会创建真实 Zoom 会议。
6. 管理界面只有回放观看人数，没有现场到场人数。
7. 临时探测脚本崩溃会在用户浏览器中留下工作标签页，必须在 `finally` 中关闭。

---

## 2026-10-02: v0.1 业务命令实现与工程落地

### 1. 今日完成工作
- **开源代码仓库与工程规范**：
  - 初始化公开 GitHub 仓库：`https://github.com/grapeot/maven-skill`（MIT 许可证）。
  - 配置主分支（`master`）保护规则：要求 Pull Request、自动化测试检查通过、0 reviewers 且 `enforce_admins=true`。
  - 基础脚手架已推送至远端仓库。
- **v0.1 只读业务 CLI 实现**：
   - 实现 `courses list`：通过首页账号菜单动态定位 Dashboard 与 Courses，提取并去重课程列表，不硬编码租户或课程路径，并报告完整性。
  - 实现 `cohorts list`：解析课程概览页班期卡片，交叉核验 Student home 链接与设置链接参数以提取 slug；实现安全的 `latest` 选期逻辑（优先 Upcoming 且强制年份比较，拒绝凭数字序号猜测）。
  - 实现 `students export`：精准筛选 Enrolled 学员，触发报表导出并进行严密数据校验（表头、全部 enrolled 状态、规范化邮箱去重、带时区时间戳、页面人数与行数一致性及非 HTML 拦截）。
  - 实现 `--auth-state` 全局选项：支持在已有 CDP 浏览器中建立临时独立 Context 隔离运行，执行完毕后安全关闭临时上下文。
  - 优化工作标签页隔离：默认业务命令在已有持久 Context 中开辟独立标签页执行，用毕即关，完全不干扰用户正在浏览的原有页面。
   - 实现收据机制：在 `.local/receipts/`（`0700`）保存 SHA-256、行数和列名等元数据（`0600`），并原子替换 `latest.json` JSON 指针文件。
- **离线测试套件扩充**：
   - 测试用例由初期的 9 项扩充至 38 项，覆盖会话安全、端口隔离、数据解析、班期选期规则、CSV 校验与工作标签页隔离；隐私扫描独立执行。
  - 自动化隐私扫描确认 `src/` 与 `tests/` 无任何内部私有路径或真实账号数据泄露。

---

## 实机实测与真实经验记录 (Lessons Learned)

实机环境下，在默认 Profile 模式下顺利完成了 `courses list`、`cohorts list` 及 `students export` 的端到端测试，生成的 Enrolled CSV 成功通过所有格式与数据校验，且原有用户标签页保持原样。

在开发与实测过程中记录的真实踩坑经验：
1. **下载图标无文本与 Accessible Name**：
   - Maven 学员列表页的导出按钮为一个纯图标按钮，不包含任何文字内容，亦未设置 `aria-label`。通过 `get_by_role("button", name="Export")` 定位会直接超时。最终通过其特定的 SVG 路径数据（`d="M8.0625 10.3135L12 14.2499L15.9375 10.3135"`）唯一定位。
2. **下载流程分为打开对话框与确认导出两步**：
   - 第一次点击下载图标仅会呼出 `Export Students` 对话框，此时并不会触发文件下载。若直接围绕首次点击等待 `download` 事件会导致超时。正确流程为：先点击图标打开对话框，核验并确保仅勾选 `Enrolled`，随后针对对话框内的 `Export Students` 确认按钮设置 `expect_download` 监听并触发点击。
3. **页面 Enrolled 人数初始加载可能为 0**：
   - 页面初始加载时，`ENROLLED (<count>)` 按钮上的数字可能暂显为 0 或需要数秒后才完成统计更新。必须增加稳定等待逻辑，并在对话框打开后，将其内部标注的 `... users` 计数与页面计数进行交叉核对，确保两处统计完全一致后再执行导出。

---

## 验证清单 (Verification Checklist)

- [x] **基础设施与会话管理**：
   - `session open`、`session status`、`session save` 实测通过；端口严格回环绑定。`session close` 已实现，尚未为验收关闭用户窗口。
- [x] **v0.1 业务命令端到端（默认 Profile）**：
  - `courses list` 动态路由与列表输出实测通过。
  - `cohorts list` 班期卡片提取与 `latest` 判定实测通过。
  - `students export` 对话框控制、Enrolled CSV 下载、格式校验与收据生成实测通过。
- [x] **自动化离线测试**：
  - 38 项单元测试与隐私检查全部通过。
- [ ] **`--auth-state` 独立 Context 登录恢复**：
   - 独立 agent 实测失败：刷新快照后 cookie 已随请求送出，但服务端清除认证 cookie。对齐 UA 仍失败，原因尚未确定；未静默回退或覆盖有效快照。
- [x] **跨 Chrome 进程重启登录态持久化**：
   - 保存关闭专用 Chrome，使用临时 headless wrapper 重启同一 profile，登录和课程发现正常。
- [x] **独立 agent 的 headless profile 验收**：
   - 从页面动态发现课程与最新 Upcoming，导出 CSV，人数、全部列值及规范化邮箱/报名时间集合与首份人工探索导出一致；文件和收据留在私有目录。此成功属于 profile 路线，不代表 auth-state 路线成功。

---

## 风险与安全红线提醒

1. **绝对只读红线**：严禁执行任何变更课程设置、修改学员状态、发送邀请或外部记账操作。
2. **严格数据隔离**：所有真实业务数据、CSV 导出文件及运行日志严格留在本地 `.local/` 目录中，严禁推入代码仓库。公共文档中仅保留虚拟示例。
3. **输出脱敏要求**：业务命令 stdout 严禁输出学员姓名与邮箱地址。
