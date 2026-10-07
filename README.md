# Maven Skill

Maven Skill 是面向 AI Agent 的 Maven（maven.com）平台浏览器自动化工具与技能包。项目基于 Playwright 驱动系统级 Google Chrome，采用“浏览器优先、人工登录、Agent 观察”架构，实现课程与班期（Cohort）动态发现，以及报名学员（Enrolled）名单 CSV 导出、格式校验与收据生成。

代码仓库：[https://github.com/grapeot/maven-skill](https://github.com/grapeot/maven-skill)，采用 MIT 许可证。

---

## 核心设计与特性

- **浏览器优先 (Browser-First)**：通过独立的持久化 Chrome Profile 让用户在真实图形界面中完成登录，规避不可靠的私有 API 逆向绑定。
- **动态路径发现**：通过 Maven 首页账号菜单动态路由至 Dashboard 与 Courses，不硬编码租户或课程路径。
- **班期智能识别与校验**：交叉核对 Student home 与 settings 链接提取 Cohort 标识（slug）；`latest` 规则优先选择唯一的 Upcoming 班期，并对带年份的日期执行严谨比较；多 Upcoming、缺少完整年份或列表不完整时拒绝靠数字大小盲目猜测。
- **严密导出校验与收据追溯**：
  - 仅导出状态为 Enrolled 的学员名单；
  - 严谨校验必需列（`email`、`status`、`enrolled_at`，11 列为当前观察到的格式而非全部必需）、行长一致性、全部 Enrolled 状态、规范化邮箱唯一性及带时区的时间戳；
  - 自动识别并拦截会话失效重定向返回的 HTML 页面；
  - 导出 CSV 默认保存为 `0600` 权限，同名文件拒绝覆盖；
  - 自动在私有 `receipts/` 目录（`0700`）写入包含 SHA-256、行列计数、观察时间与绝对路径的收据文件并更新 `latest.json` 指针。
- **标签页与上下文隔离**：
  - 默认业务命令在已有持久 context 中开启独立工作标签页，执行完毕后自动关闭该标签页，保持用户原有标签页原封不动；
  - 支持全局 `--auth-state FILE` 选项（必须置于子命令前），基于存储状态建立临时独立 context 执行，完成即销毁临时 context。
- **低特权与隐私保护**：CDP 仅监听本地回环地址（`127.0.0.1`）；所有数据与状态严格限制在本地私有目录；业务命令 stdout 仅输出统计指标与文件路径，不打印学员姓名或邮箱。

---

## 环境要求

- Python 3.12+
- 系统中已安装 Google Chrome（在 `PATH` 中或通过环境变量指定）
- 包管理与虚拟环境工具：`uv`

---

## 安装与初始化

1. 克隆代码仓库并进入目录：
   ```bash
   git clone https://github.com/grapeot/maven-skill.git
   cd maven-skill
   ```

2. 创建并激活虚拟环境：
   ```bash
   uv venv --python 3.12
   source .venv/bin/activate
   ```

3. 安装项目及开发依赖：
   ```bash
   uv pip install -e '.[dev]'
   ```

4. 运行离线单元测试：
   ```bash
   pytest
   ```

---

## 配置与环境变量

CLI 支持命令行参数与环境变量注入。请注意：**CLI 工具不会自动加载 `.env` 文件**，配置需由外部 shell 或环境管理工具注入。

| 命令行选项 | 对应环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `--data-dir` | `MAVEN_DATA_DIR` | `.local` | 运行期数据存储目录。相对路径相对于当前工作目录（cwd）；跨目录调用请使用绝对路径 |
| `--port` | `MAVEN_CDP_PORT` | `9337` | Chrome CDP 远程调试监听端口 |
| *(无特定选项)* | `MAVEN_CHROME_EXECUTABLE` | 系统默认位置 | Google Chrome 可执行文件路径 |
| `--auth-state` | *(无)* | *(无)* | 全局选项，指定认证状态快照文件路径（必须写在子命令前） |

---

## 命令行接口 (CLI)

CLI 统一入口为 `maven-skill`，执行结果均输出标准 JSON。

### 1. 会话管理 (`session`)

- **打开会话**：
  ```bash
  maven-skill session open [--url https://maven.com/]
  ```
  唤起绑定独立 Profile（默认 `.local/browser-profile`）的 Chrome 实例。若已有会话运行，直接复用连接且不覆盖用户当前停留在浏览器中的页面。

- **检查会话连接**：
  ```bash
  maven-skill session status
  ```
  检查 CDP 端口连通性。该命令仅表明调试端口可达，不代表 Maven 平台处于登录状态。

- **保存认证快照**：
  ```bash
  maven-skill session save
  ```
  从当前运行的浏览器中导出 Cookies、localStorage 和 IndexedDB 至 `.local/auth-state.json`（权限 `0600`）。

- **关闭会话**：
  ```bash
  maven-skill session close
  ```
  先自动执行状态保存，随后关闭 Chrome 浏览器进程。

### 2. 页面观察 (`page`)

- **捕获页面文本快照**：
  ```bash
  maven-skill page snapshot
  ```
  提取最后一个 Maven 标签页的可见文本与主要控件信息。快照可能包含个人信息，仅供本地分析。

- **页面定向跳转**：
  ```bash
  maven-skill page goto <URL>
  ```
  驱动最后一个 Maven 标签页跳转至指定 URL（仅限 `maven.com` 域下的 HTTPS 链接）。

### 3. 业务操作 (`courses` / `cohorts` / `students`)

- **列出课程**：
  ```bash
  maven-skill courses list
  ```
   自动从 Maven 首页账号菜单进入 Dashboard，访问 Courses 列表并去重输出课程链接与标题。支持链接型分页；遇到无法自动遍历的下一页按钮时报告 `completeness.status=partial`，不能将部分结果视为全量。

- **列出班期 (Cohorts)**：
  ```bash
  maven-skill cohorts list --course <COURSE_ADMIN_URL>
  ```
   进入指定课程管理页，解析观察到的班期卡片、识别 `latest` 候选，并输出 slug、状态、开始日期与页面日期文字。出现分页控件时报告 partial，导出不允许从 partial 列表推断 latest。唯一 Upcoming 可直接选择；比较多个日期时要求完整年份。

- **导出学员名单 CSV**：
  ```bash
  maven-skill students export --course <COURSE_ADMIN_URL> --cohort latest [--output <PATH>]
  # 或指定具体班期 slug
  maven-skill students export --course <COURSE_ADMIN_URL> --cohort <COHORT_SLUG> [--output <PATH>]
  ```
  进入学员管理页面，过滤并确认 Enrolled 状态，触发报表导出下载并执行全面数据格式校验。输出包含校验摘要、行数统计、SHA-256 与收据路径。

- **使用独立认证状态执行业务命令**：
  ```bash
  maven-skill --auth-state .local/auth-state.json courses list
  ```
  全局参数 `--auth-state` 必须置于子命令之前。该模式在已有 CDP 浏览器中建立临时 context，完成数据提取后即时销毁临时 context，不影响其他标签页。

  **认证快照加载属于实验路径。** 独立实机验收中，刚刷新的 cookie 快照虽然随请求送出，Maven 首页仍返回未登录状态并清除认证 cookie；复用持久 profile 则可以正常查询和导出。原因尚未确定，不应归因为单纯过期或浏览器指纹。快照模式失败时不要覆盖有效快照，也不要静默切换凭证来源；明确选择默认 profile 路线继续，必要时人工重新登录。

持久 profile 已通过关闭 Chrome 后重启的登录复用，以及独立 agent 的 headless CSV 导出验收。临时 headless 可由本地 Chrome 启动 wrapper 加入 `--headless=new`，经 `MAVEN_CHROME_EXECUTABLE` 指定；登录配置仍默认可见窗口，公开 CLI 默认行为不变。

### 4. Lightning Lesson 只读命令 (`lessons`)

- **列出 lesson**：
  ```bash
  maven-skill lessons list
  ```
  从账号菜单动态进入 Dashboard 与 Lightning Lessons 列表，输出每个 lesson 的 ID、标题、状态（`draft` / `upcoming` / `past`）、管理页 URL，以及卡片上可见的日期时间与报名人数；分组计数对不上时报告 `completeness.status=partial`。

- **查看单个 lesson**：
  ```bash
  maven-skill lessons show --lesson <LESSON_ID_OR_ADMIN_URL>
  ```
  读取编辑器字段（标题、日期、开始时间、时区、时长、outcome 与 `topic_desc` 的字符数对照上限、讲师姓名）、完成度、`Review N errors`、标记错误的卡片与推导出的发布阻断项；已发布 lesson 另从页面内嵌数据读取聚合字段。事件链接只输出布尔值。

- **聚合统计**：
  ```bash
  maven-skill lessons stats --lesson <LESSON_ID_OR_ADMIN_URL>
  maven-skill lessons stats --all
  ```
  输出报名数（页面内嵌数据与 Signups 标签页标题两个来源）、回放观看数与合计。报名日期直方图不提供：精确报名时间只能来自未公开 API，本工具不调用。

lessons 命令只导航和读取：所有 lesson 页面经只读门面访问，没有点击或输入接口，Publish、Create a Zoom meeting、Delete instructor、Save 等控件被点击守卫拒绝。stdout 输出前统一扫描，含邮箱或会议链接时拒绝打印。

### 5. 课程评价只读命令 (`reviews`)

- **公开评价**：
  ```bash
  maven-skill reviews list --course https://maven.com/<school>/<course>
  ```
  读取课程公开落地页上的全部学员评价（点击 `Show more reviews` 打开抽屉并逐页加载）与讲师精选 testimonial。每条评价输出页面显示名、头衔·公司、班期标签、日期、0–5 评分（首页来自内嵌数据，其余来自星标图标，支持半星）与全文；另输出课程总评分（内嵌数据 0–10 分制换算，并与页面 `X.X (N ratings)` 交叉核对）与完整性。也接受课程管理页 URL。

- **班期问卷评分**：
  ```bash
  maven-skill reviews surveys --course <COURSE_ADMIN_URL> [--download [--cohort <LABEL|N>] [--output-dir <DIR>]]
  ```
  从课程 Surveys 页读取各班期 post-course survey 的平均分、回复数与完成日期。加 `--download` 时通过页面自带的 `N responses` 按钮把各班期问卷 CSV 保存到私有目录（`0600`、拒绝覆盖、带收据，不改动 `students export` 的 `latest.json` 指针），stdout 只输出评分直方图、公开评价/私下留言人数等聚合。

两个命令都不回复、不发布、不隐藏评价。`reviews list` 输出的是公开页面已展示的内容（含评价者显示名）；问卷 CSV 中的姓名、邮箱与私下留言只留在本地。详见 [`skills/maven/references/reviews.md`](skills/maven/references/reviews.md)。

### 6. 折扣码只读命令 (`promo-codes`)

- **列出折扣码与状态**：
  ```bash
  maven-skill promo-codes list --course https://maven.com/<school>/admin/courses/<course> [--json]
  ```
  读取课程 Settings 页的 Promo codes 表格，逐行输出 code、amount off、percent off、redemptions 与 status（`active` / `paused` / `unknown`）。status 综合三个信号：切换按钮图标的几何形状（双竖条 / 三角形）、行是否置灰（`text-gray-400`）、页面 React 数据中按行对齐的 `active`（可选，读不到时降级而不报错）；信号不一致时报 `unknown`。同时标记大小写不敏感的重复码。默认输出文本表格，`--json` 输出完整结构。`--course` 也接受 `<school>/<course>` 或裸课程 slug（裸 slug 经账号菜单发现课程）。

- **定位某个码的暂停按钮**：
  ```bash
  maven-skill promo-codes locate-pause --course https://maven.com/<school>/admin/courses/<course> --code <CODE> --output-dir <DIR> [--json]
  ```
  要求该码在表中唯一、该行恰好 3 个按钮，用四项检查（图标几何、onClick 源码含 `active` 切换与 `"Paused"`、另两个按钮分别是复制链接和删除、当前 active）识别暂停按钮：四项都过为 `high`，缺 React 数据为 `medium`；码已暂停时报 `already_paused`。在输出目录写入行截图 `row.png`、用 PIL 框出按钮的 `annotated.png`（不改 DOM）与 `evidence.json`，并用无 cookie 的 context 打开 `?promoCode=` 公开链接记录划线价基线。退出码：`ready_to_pause` / `already_paused` 为 0，`not_ready` 为 3。`--course` 只接受课程管理页 URL 或 `<school>/<course>`。

两个命令都不点击 Actions 列任何按钮、不在 Settings 页输入任何内容；Settings 页只经没有点击、输入、hover 接口的只读门面访问。暂停本身是业务写入，CLI 不实现。输出含真实码名与额度，只留在本地。详见 [`skills/maven/references/promo_codes.md`](skills/maven/references/promo_codes.md)。

### 7. Lightning Lesson 参考

[`skills/maven/references/lightning_lessons.md`](skills/maven/references/lightning_lessons.md) 记录了 Lightning Lesson 管理界面的导航路径、编辑器字段限制（标题 ≤ 60、outcome 描述 ≤ 120、`topic_desc` ≤ 450 等）与行为坑点（字段自动保存、创建与删除讲师无确认、事件链接是硬性发布阻断项）。CLI 只提供上面的只读 `lessons` 命令，不实现任何编辑器写入；Publish、创建 Zoom 会议、邮件与课程级折扣码写入默认由人类操作。

### 8. Promo Code（折扣码）参考

[`skills/maven/references/promo_codes.md`](skills/maven/references/promo_codes.md) 记录了课程 Settings 页 Payments 组内 Promo codes 区块的结构：常驻内联创建表单（`input[name="code"]`、`amount_off` 与 `percent_off` 二选一的 `OR` 规则、提交按钮 `Create promo code`）、已有码表格（Code / Amount off / Percent off / Redemptions / Actions）与相关坑点。Actions 列中间按钮是暂停/恢复切换：单击即生效、没有确认框，重复点击会重新激活；删除按钮有浏览器原生 confirm。暂停的行整行置灰，图标随状态在双竖条与三角形之间切换。表中可能有同名重复码，按码查找必须校验唯一，数据按行而不是按码文本配对。暂停是否生效可用无 cookie 打开 `?promoCode=` 公开链接验证：激活的码显示划线价，暂停后划线价消失。折扣码属于课程、对全部班期生效，可删除或暂停，不支持 100% off。带折扣的分享链接格式是落地页加 `?promoCode=<CODE>`（已实测；`?coupon=` 等写法不生效），详见参考文档。

经授权实测创建的坑点：Code 只接受字母、数字、连字符（含下划线会被客户端校验拒绝，且不发出请求、无弹窗，表现为「点了没反应」）；已观察到校验失败只显示内联提示的情况，因此不能只靠有无弹窗判断成败；金额字段是 React 受控输入，若脚本填写后点击无效可用原生 setter + 事件强制写入；`amount_off` 填整数；新建行 Redemptions 初值为 `-`；验收须刷新页面复验新行仍在。

CLI 只提供上面的只读 `promo-codes` 命令，没有创建、暂停或删除 promo code 的命令，也不实现任何此类写入。只读核对（导航到 Settings、读取 Promo codes 区块与表格）无需授权；创建、暂停、删除折扣码都属于业务写入，CLI 不实现，默认由人类操作，Agent 仅在用户对具体动作单独显式授权后才可协助。参考文档与操作步骤本身不构成授权。

### 9. 主 Skill 结构与参考

[`skills/maven/SKILL.md`](skills/maven/SKILL.md) 按 **runbook** 组织：一个「前置会话闸 + 任务路由表」的骨架，把每个任务的细节下沉到 `skills/maven/references/` 下。会话连通是唯一串行前置，其余任务按需单独执行，不必按顺序走。

| 参考文件 | 内容 |
|---|---|
| [`references/session.md`](skills/maven/references/session.md) | 会话命令语义、环境变量、`--auth-state` 隔离上下文、headless 运行 |
| [`references/courses_cohorts.md`](skills/maven/references/courses_cohorts.md) | 课程/班期发现契约与 `latest` 选期规则 |
| [`references/students_export.md`](skills/maven/references/students_export.md) | `students export` 的命令、标签页生命周期、CSV 校验与收据 |
| [`references/lightning_lessons.md`](skills/maven/references/lightning_lessons.md) | Lightning Lesson 管理界面契约、CLI 输出语义与坑点 |
| [`references/reviews.md`](skills/maven/references/reviews.md) | 公开评价与班期问卷评分的读取契约、评分换算与隐私边界 |
| [`references/promo_codes.md`](skills/maven/references/promo_codes.md) | 折扣码区块、Actions 按钮身份、`promo-codes` 只读命令与写入授权边界 |


---

## 安全与隐私规范

1. **严格回环绑定**：CDP 控制端口等同于浏览器完全控制权，严格绑定于 `127.0.0.1`，禁止外网暴露。
2. **文件系统权限隔离**：
   - 运行期数据目录权限为 `0700`；
   - 导出 CSV、认证快照文件及收据文件权限为 `0600`；
   - 导出的 CSV 文件若已存在，拒绝覆盖已有文件。
3. **敏感文件全量忽略**：`.local/` 目录、下载文件、运行日志及 `.env` 均加入 `.gitignore`，严禁提交到代码仓库。
4. **只读业务边界**：本工具仅用于只读观察、名单导出、Lightning Lesson 只读查看、课程评价读取与折扣码状态读取。严禁修改课程或学生数据，严禁发送邀请，严禁调用任何外部结算或记账写入接口。
5. **脱敏与脱密**：业务命令 stdout 绝不打印学员姓名与邮箱（`reviews list` 仅输出公开页面已展示的评价者显示名）。公共仓库中仅使用虚拟示例。

---

## AI Agent Skill 安装说明

在将本工具集成到 AI Agent 工作区（如 Codex、Claude Code、Cursor 或 OpenCode）时：

1. 每个工作区仅将 `skills/maven/SKILL.md` 挂载为唯一根技能。
2. 查阅宿主工作区的路由规范（如 `rules/skills/INDEX.md` 或 `AGENTS.md`）完成登记。
3. 任何与私有账号别名、本地路径或专属环境配置相关的设置，均保留在宿主工作区的私有 overlay 中，不得提交至公共仓库。
