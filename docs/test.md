# 测试与验证规范 (Test Specification)

本文档记录 `maven_skill` 的测试策略、自动化离线测试套件及实机环境下的验证状态。

---

## 1. 测试策略与原则

- **离线测试优先**：自动化测试严禁向外部网络或真实 `maven.com` 发出请求，所有测试用例均基于离线 Mock、局部数据结构解析与临时本地文件系统执行。
- **严格的安全与权限断言**：测试重点覆盖端口隔离、会话防错连、文件系统权限掩码（`0700`/`0600`）及数据去敏。
- **事实与状态清晰切分**：明确区分已通过离线测试验证的特性与待实机验证的特性，不做出超越已证事实的断言。

---

## 2. 自动化离线测试套件 (Offline Test Suite)

执行命令：
```bash
source .venv/bin/activate
pytest
```
当前套件共包含 **138 项自动化测试**（含参数化用例），全部保持通过。

### 2.1 会话管理与 CDP 安全测试 (`tests/test_session.py`)
- **导航 URL 安全过滤**：限制仅允许 `maven.com` 域名下的 HTTPS 链接，阻断非 Maven 域、HTTP 协议以及携带账号密码凭据的 URL。
- **认证快照原子写入与权限**：验证 `private_json` 通过临时文件与原子替换写入，断言生成的快照文件权限严格为 `0600`。
- **Profile 冲突防御**：模拟非目标 Chrome 实例，断言 CLI 会通过 CDP 读取 `Browser.getBrowserCommandLine` 并拒绝连接不匹配的 Profile 目录。
- **端口解析与配置错误脱敏**：验证字符串端口转换、合法端口范围（1024-65535）校验；断言无效端口环境变量错误信息经过脱敏，不回显具体异常输入。
- **断连状态语义**：验证在 CDP 端点未就绪时，`session status` 明确返回 `browser_connected: false` 与 `authentication: "not_checked"`，杜绝假定已认证。

### 2.2 数据解析与业务逻辑测试 (`tests/test_parse.py`)
- **课程列表去重与文本净化**：验证重复课程链接根据规范化 URL 去重，保留完整标题，并过滤潜在的邮箱等敏感文本。
- **班期卡片与 Slug 交叉校验**：验证从 Student home 链接与 settings 链接同时提取 slug；二者不一致时报错拒绝；存在重复 slug 时拒绝处理。
- **`latest` 选期严谨性**：
  - 存在唯一个 Upcoming 班期时准确识别；
  - 多个 Upcoming 班期在包含年份时按年月日精确比较；
  - 日期缺少完整年份时，拒绝仅凭月份大小排序；
  - 日期并列时拒绝通过数字 slug 猜测；
  - 当班期列表状态为 `partial`（分页未完全加载）时，拒绝执行 `latest` 选期。
- **学员管理 URL 构建**：验证根据导航链接准确替换 `?cohort=<slug>` 参数。
- **CSV 数据格式与安全性校验**：
  - 校验必需列（`email`、`status`、`enrolled_at`），兼容观察到的 11 列格式；
  - 拦截 HTML 登录重定向假 CSV；
  - 校验数据行数与页面计数完全匹配；
  - 校验全部行状态必须为 enrolled；
  - 校验规范化邮箱唯一性，拦截重复邮箱行；
  - 校验 `enrolled_at` 必须为带时区的合法时间戳；
  - 拦截表头缺失、行长不一致及多余列等格式异常。
- **输出文件防覆盖与权限**：验证 `reserve_output` 以 `0600` 模式独占创建文件；若目标文件已存在，报错拒绝覆盖。
- **发布前隐私审阅**：独立运行 `python scripts/privacy_review.py`，扫描 Git 可发布文件中的非示例邮箱、个人路径、私钥及当前保存的 cookie 值；再人工核对差异中的课程、客户和运行数据。脚本不代替人工检查。

### 2.3 工作标签页与上下文隔离测试 (`tests/test_ops_isolation.py`)
- **默认工作标签页隔离**：验证在已有持久 Context 中打开新工作标签页，执行完毕后仅关闭新标签页，原有标签页、Context 及浏览器进程原样保持。
- **`--auth-state` 上下文隔离**：验证基于状态快照创建全新的独立 Context，执行完毕后关闭临时 Context，完全不影响主 Context。
- **快照文件不存在处理**：传入不存在的快照路径时报错退出，不触发任何浏览器上下文创建。

### 2.4 Lightning Lesson 只读命令测试 (`tests/test_lessons.py`)
- **列表解析**：手写虚拟分组数据，验证状态、日期时间与报名数解析；分组数量不符、未知分组、游离卡片、翻页控件或非 lesson 链接时报告 partial。
- **lesson 引用**：接受 ID、管理页 URL、`/edit` 与带 `tab` 的 URL；拒绝非 maven.com、非 HTTPS、非 lesson 路径与不安全 ID。
- **字段与上限**：优先使用页面 `N/M` 计数器，否则按默认上限计算；超限、缺链接、`data-error` 卡片、`Review N errors`、完成度与“完成后页头只剩 Publish”的判定。
- **已发布聚合数据**：只保留聚合字段，`phase` 判定（past / upcoming / canceled），异常计数类型置空；输出中不含会议链接。
- **隐私断言**：标题、讲师名、行内错误中的邮箱被丢弃；`assert_public_output` 对邮箱、`zoom.us` 与 `pwd=` 拒绝输出；命令级测试断言 stdout JSON 中无邮箱。
- **点击守卫与只读门面**：拒绝 Publish、Create a Lightning Lesson、Create a Zoom meeting、Delete instructor、Save 等标签与写入动词；`ReadOnlyPage` 不暴露 click / fill / type / keyboard / locator 等接口，只执行登记过的脚本，只导航到 maven.com；静态检查登记脚本不含 `.click(`、赋值、`fetch` 等写入模式。
- **命令编排**：用记录调用的假页面跑 `list` / `show` / `stats`，断言零点击零输入；管理页 URL 跳过组织发现；内嵌数据属于其他 lesson 时拒绝；草稿 stats 报告未发布。
- **生命周期与 CLI**：命令失败时工作标签页仍关闭；`stats` 必须且只能指定 `--lesson` 或 `--all`；意外异常输出经脱敏，不含 token、邮箱或路径。

---

## 3. 实机验证状态清单 (Empirical Verification Status)

| 验证项 | 验证内容与目标 | 状态 | 验证结论与说明 |
|---|---|---|---|
| **Chrome 进程唤起与 CDP 回环** | 验证 `session open` 唤起系统 Chrome 并监听 `127.0.0.1:9337` | 已实测通过 | 系统 Chrome 正确启动，端口回环监听，重复调用返回 `reused=true` |
| **人工登录与凭据保存** | 用户在图形界面完成登录，`session save` 导出状态 | 已实测通过 | 用户成功登录 Maven，导出的快照文件权限为 `0600` |
| **默认 Profile 业务命令实测** | 验证 `courses list`、`cohorts list` 及 `students export` | 已实测通过 | 课程列表与班期解析正确，Enrolled CSV 成功下载并通过全部数据校验，原用户标签页完好保留 |
| **`--auth-state` 独立上下文实机验证** | 在同一 Chrome 中建立新 context，载入快照并认证 | 认证失败 | 新鲜 cookie 已发送但被服务端清除；不能静默回退 profile 或覆盖有效快照 |
| **跨 Chrome 重启登录态保持** | 关闭后重启同一 profile，验证是否保留登录 | 通过 | 临时 headless Chrome 中登录保持，业务查询正常 |
| **Lightning Lesson 只读命令** | `lessons list`、草稿与已结束 lesson 的 `lessons show`、`lessons stats --lesson` 与 `--all` | 已实测通过 | 列表完整性 complete；字段、计数器、链接布尔值、发布错误与聚合统计正确；输出无邮箱与会议链接；运行前后浏览器标签页集合一致，未修改任何 lesson |
| **独立 agent headless 导出** | 动态发现课程、选择 latest、导出并与首份 CSV 比较 | 通过 | 行数、全列值、规范化邮箱/时间集合一致，输出与 receipt 私有；仅验证 profile 路线 |
