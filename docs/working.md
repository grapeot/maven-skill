# Working Notes: Maven Skill

本文档用于跟踪 `maven_skill` 项目的开发进度、架构决策与待实测验证项。

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
