# 测试与验证规范 (Test Specification)

本文档记录 `maven_skill` 的测试策略、自动化离线测试套件及需要实机参与的待实测验证项。

---

## 1. 测试策略与原则

- **离线测试优先**：日常开发、CI 与自动化验证均基于离线 Mock 或本地独立临时实例进行，严禁向外网或真实的 `maven.com` 发出真实请求。
- **权限与隔离防线**：重点验证端口冲突防御、进程状态重连以及文件系统权限掩码。
- **区分自动化断言与实机待测项**：尚未进行实测的业务特性，明确归类为待实测项，不编造测试断言。

---

## 2. 自动化离线测试项 (Offline Test Suite)

运行命令：
```bash
source .venv/bin/activate
pytest
```

### 2.1 CLI 配置与参数解析测试
- **参数优先级**：验证命令行参数（`--port`、`--data-dir`）优先于环境变量（`MAVEN_CDP_PORT`、`MAVEN_DATA_DIR`），环境变量优先于默认值（`9337`、`.local`）。
- **JSON 输出契约（后续覆盖目标）**：命令结果写 stdout，操作异常写 stderr JSON 并返回非零退出码；argparse 的 help/参数错误沿用标准终端格式。

### 2.2 端口与实例隔离测试 (Port & Profile Isolation)
- **避免误连其他 Chrome**：
  - 构造非 Maven Skill 管理的本地占用端口（例如非 CDP 协议的 HTTP 服务或开发服务器）。
   - 非 CDP 服务视为未连接；`session open` 对已占用端口拒绝启动。有效 CDP 连接仍须验证精确 profile 路径。
- **自定义端口与独立 Profile**：
  - 验证传入自定义 `--port 9338 --data-dir .local/test-dir` 时，能够严格定位到独立的目录与端口，不与默认会话产生混淆。

### 2.3 文件系统权限安全测试
- **目录权限测试**：
  - 测试创建运行时目录逻辑，断言新建的数据目录及其子目录（`browser-profile`）的文件模式严格满足 `0700`。
- **快照权限测试**：
  - 测试 `session save` 生成 `.local/auth-state.json` 的逻辑，断言新建文件的模式严格满足 `0600`（避免同机非特权用户读取 Cookie）。

### 2.4 新进程重连测试 (Fresh Process Reconnect)
- **场景**：模拟后台 Chrome 进程已经以 `--remote-debugging-port` 启动并处于等待状态。
- **验证点**：
  - 发起一个全新的 Python 独立进程调用 CLI。
  - CLI 能够在不重新拉起新 Chrome 窗口的前提下，快速建立 CDP WebSocket 连接。
  - 发送 `page snapshot` 或 `session status` 指令并成功返回结果。
  - 验证过程中原有 Chrome 窗口未被关闭，且当前页面未被重载。

---

## 3. 待实测验证清单 (Pending Empirical Verification)

以下测试项目涉及真实的人机交互或依赖 Maven 平台服务端响应，需要人类操作者在真实环境下配合完成：

| 测试项 | 验证目标 | 当前状态 | 验收标准与注意事项 |
|---|---|---|---|
| **人工登录流程** | 验证真实用户在弹出的 Chrome 实例中通过 Google 或邮箱登录 Maven | 待实测 | 浏览器正常渲染登录页，第三方 SSO 重定向无异常，登录成功后跳转至个人 Dashboard |
| **跨重启会话恢复** | 验证关闭 Chrome 进程后，重新执行 `session open` 能否恢复登录态 | 待实测 | 杀掉 Chrome 进程后再次打开，直接进入 Dashboard，无需再次人工输入密码或验证码 |
| **真实页面快照提取** | 验证 `page snapshot` 在真实 Maven 页面上的渲染完整性与表现 | 待实测 | 提取的文本包含当前 Cohort 名称与导航标签，且敏感信息在日志中得到合理提示与保护 |
| **加载 JSON 状态至全新浏览器** | 验证 `.local/auth-state.json` 是否能在抹除 Profile 的新浏览器中复现登录态 | 待实测（当前不开放） | 仅作为技术可行性预研。在未实测前，严禁宣称支持基于该 JSON 的自动会话恢复 |
| **Cohort 列表与分页机制** | 验证真实学员/班期列表的加载形式（分页组件 vs 滚动加载） | 待实测 | 明确具体 DOM 结构，形成选择器文档与翻页等待策略 |
| **CSV 导出下载流拦截** | 验证真实报表下载行为与文件落地逻辑 | 待实测 | 拦截下载并保存至本地私有目录，校验文件内容为真实 CSV 而非重定向 HTML 登录页 |
