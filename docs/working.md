# Working Notes: Maven Skill

本文档用于跟踪 `maven_skill` 项目的开发进度、架构决策与待实测验证项。

---

## 2026-10-02: 项目初始化与骨架搭建 (Scaffold Phase)

### 1. 今日完成工作
- **项目结构与设计固化**：
  - 确定 Python 3.12+ 依赖标准，包名 `maven_skill`，命令行入口 `maven-skill`。
  - 确立基于 Playwright 驱动本地 Google Chrome 的底层架构方案。
  - 确立“持久化 Profile 为主，认证状态 JSON 快照为辅”的双层会话管理模型。
- **文档体系建立**：
  - 完成 `README.md`：概述、安装指南、配置说明、CLI 语法及 Agent Skill 安装规范。
  - 完成 `AGENTS.md`：面向 AI Agent 的版本控制纪律、Python 虚拟环境管理、隐私边界及业务只读红线。
  - 完成 `docs/prd.md`：产品需求文档，明确功能规格、边界及分期验收标准。
  - 完成 `docs/rfc.md`：技术设计说明，深度阐述 Session / Profile / Auth State 职责及安全架构。
  - 完成 `docs/test.md`：测试规范，包含离线单元测试用例设计与实机待测项清单。
  - 完成 `skills/maven/SKILL.md`：标准化 Agent 技能规范，定义目标、资源、输出契约与安全原则。

---

## 当前状态与待实测验证项 (Pending Verification Checklist)

Session 基础设施已实现并完成下述本机验证；Maven 登录后的业务页面仍待用户登录后探索。

## 验证记录（2026-10-02）

- `python -m pytest tests -q`：9 passed，覆盖 Maven URL 限制、拒绝 URL 内凭证、快照原子写入与 0600 权限、错误 profile 拒绝、断连状态。
- `session open` 已启动可见 Chrome；独立进程 `session status`、`page snapshot`、重复 `session open` 接入成功，重复打开返回 `reused=true` 且保持页面。
- `session save` 已导出状态 JSON，实际目录权限 0700、状态文件权限 0600；此时尚未人工登录，不代表已有有效 Maven 账号凭证。
- `lsof` 核实 CDP 仅监听 `127.0.0.1:9337`。
- `git check-ignore` 验证 profile Cookies、认证快照、下载 CSV、页面快照及 `.env` 均忽略。
- 公共源码与文档隐私扫描仅命中测试中的虚拟 URL 凭证示例，无真实账户或本机私有路径。
- 已根据首页实际 Log In 链接进入登录页，窗口保持打开，等待人工登录。
- 独立本地 master Git 已初始化；未提交、未创建远端仓库。
- 用户随后完成人工登录；经账号菜单进入 Dashboard → Courses → course → Students，已验证课程/cohort 观察。具体账号路径和业务数据仅保留在 `.local/`。
- 下载图标打开 Export Students 对话框，核对默认 Enrolled 筛选后点击确认；CSV 成功落盘，字段与当前消费方所需的 email/status/enrolled_at 相符，消费方只读 dry-run 通过。
- 登录后的 `session save` 再次成功；未关闭浏览器，不宣称跨重启登录已验证。

## Lessons Learned

- Students 的下载按钮没有文本。按 Export 文本定位按钮会超时；先观察实际 DOM，点击下载图标打开 dialog。
- 点击下载图标只打开选择范围的对话框。围绕第一次点击等待 download 会超时；需要在对话框内确认导出时监听下载事件。

- [x] **Google Chrome 启动与 CDP 连通性联调**：
  - 验证 `session open` 能够成功唤起系统已安装的 Chrome，并正确应用 `--user-data-dir` 与 `--remote-debugging-port`。
  - 验证 `session status` 在不同端口状态下的探测逻辑与容错。
- [ ] **人工登录与持久化 Profile 保持**：
  - 人工在弹出的 Chrome 实例中完成 Maven 平台真实账号登录。
  - 关闭浏览器进程后重新执行 `session open`，验证登录态是否持久保存在 `.local/browser-profile` 中，无需重复输入凭据。
- [x] **认证状态快照生成与权限审计**：
   - `session save` 写入成功，文件权限为 `0600`；登录凭证有效性待人工登录后验证。
- [ ] **页面观察与跳转**：
  - 运行 `page snapshot` 提取真实 Maven 页面文本，评估脱敏需求与内容解析质量。
  - 运行 `page goto` 跳转至特定 Cohort 页面，确认页面跳转无卡死或无响应现象。
- [ ] **业务逻辑预研 (Phase 2 准备)**：
  - 调查真实 Cohort 列表的 DOM 结构（是翻页器还是无限滚动）。
  - 调查报表 CSV 导出的实际交互逻辑与下载流，准备设计专属业务命令。

---

## 风险与开发守则提醒

1. **选择器严禁臆测**：在未连接真实浏览器查验 DOM 之前，代码库与文档中不硬编码任何 Maven 业务选择器。
2. **只读操作红线**：当前阶段仅限于页面观察与状态探测，严禁执行任何写入、更新或邀请发送。
3. **私密数据防外流**：`.local/` 目录严禁提交至版本控制；公共文档中仅保留虚拟示例。
