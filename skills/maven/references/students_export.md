# 学员名单导出参考 (`students export`)

本文档记录 `maven-skill students export` 命令的操作说明、内部标签页契约、CSV 数据校验规则与审计收据生成规范。

---

## 1. 命令用法

`students export` 支持针对最新班期（`latest`）或指定班期 slug 导出已报名的 Enrolled 学员名单：

```bash
# 导出最新班期学员名单
maven-skill students export --course <COURSE_ADMIN_URL> --cohort latest [--output <PATH>]

# 导出指定班期学员名单
maven-skill students export --course <COURSE_ADMIN_URL> --cohort <COHORT_SLUG> [--output <PATH>]
```

参数说明：
- `--course <COURSE_ADMIN_URL>`：课程管理页面 URL。
- `--cohort latest|<COHORT_SLUG>`：班期标识。`latest` 的选择逻辑不止「唯一 Upcoming」，完整规则见 [课程与班期发现参考](courses_cohorts.md)（优先唯一 Upcoming；多个 Upcoming 按完整年份日期选最新；无 Upcoming 时从非 `self_paced` 的带日期班期选最新；缺年或并列拒绝；班期列表 `partial` 时拒绝推断 `latest`）。亦可明确传入班期 slug。
- `--output <PATH>`：（可选）指定导出 CSV 文件的存储路径。省略时保存至默认数据目录。

---

## 2. 内部执行流程与标签页生命周期

为了保证操作安全且不干扰用户当前界面，CLI 遵循以下内部交互契约：

1. **独立临时工作标签页**：在当前浏览器上下文中自动建立独立临时工作标签页，导航至学员管理页面，等待页面的 Enrolled 学员计数稳定。课程级导航有 Students 时用 `students?cohort=<slug>`；2026-10 起的页面结构没有课程级 Students，改用班期自己的 `cohorts/<slug>/students`。
2. **打开导出对话框**：定位并点击学员列表上方的无文本导出图标按钮，打开 `Export Students` 对话框。
3. **确认筛选条件与人数**：在对话框中确保仅勾选 `Enrolled` 状态选项，核对勾选后的人数与页面计数一致。
4. **触发下载与拦截保存**：点击确认导出，通过 CDP 拦截并保存下载的 CSV 文件流。
5. **自动关闭工作标签页**：操作无论成功或异常退出，工作标签页均在 `finally` 中自动关闭，用户原有正在浏览的标签页保持原貌。

---

## 3. CSV 严密校验契约

拦截保存下载文件后，CLI 对原始 CSV 数据执行全量校验，任何一项未通过均报错拦截：

- **必需列检查**：必需包含 `email`、`status`、`enrolled_at` 三列（兼容当前观察到的全量 11 列格式，行长必须一致）。
- **状态一致性**：CSV 内全部学员行的 `status` 必须为 `enrolled`，杜绝混入其他状态。
- **邮箱唯一性与规范化**：对所有邮箱做小写与去除空格规范化，确保学员邮箱无重复。
- **带时区时间戳**：`enrolled_at` 时间戳必须带有时区信息，确保时间解析无歧义。
- **总行数与页面计数一致**：CSV 实际数据行数必须与页面观察到的 Enrolled 人数完全一致。
- **拦截重定向 HTML**：若会话失效导致下载内容为登录页重定向 HTML，立即识别并拦截报错，严禁写入伪造 CSV。

---

## 4. 文件安全与审计收据 (`receipts/`)

- **文件系统权限**：
  - 导出的 CSV 文件权限设置为 `0600`。
  - 同名文件保护：若目标路径已存在同名文件，CLI 拒绝覆盖已有文件。
- **审计收据追溯**：
  - 每次成功导出后，CLI 自动在私有 `receipts/` 目录（目录权限 `0700`）中生成收据 JSON 文件。
  - 收据文件权限为 `0600`，内容包含：导出的 CSV 文件绝对路径、文件大小、SHA-256 校验和、有效数据行数及页面观察时间戳。
  - 自动更新 `receipts/latest.json` 指针，指向最新生成的收据。

---

## 5. 零 PII 原则 (Zero-PII)

- **输出限制**：CLI stdout 与向用户的汇报回复中，**严禁打印任何学员的真实姓名或邮箱地址**。
- **输出内容**：仅输出操作摘要（课程 URL、班期 slug）、Enrolled 人数、CSV 相对路径、文件大小与 SHA-256 校验和。

---

## 6. 看学员的职位、公司与报名动机（听众画像）

Maven 没有单独的「学员资料」导出。学员的职位、公司等信息就在 `students export` 导出的 CSV 里，不需要逐个点开学员详情页。截至 2026-10 观察到的 11 列：

| 列 | 含义 | 备注 |
|---|---|---|
| `full_name`、`preferred_name` | 姓名、称呼 | PII |
| `email` | 报名邮箱 | PII；Ledger 等下游用它做主键 |
| `status` | 报名状态 | 导出只含 `enrolled` |
| `company` | 公司 | 学员自填，可能为空 |
| `job_title` | 职位 | 学员自填，可能为空，写法不统一（如 `ML Engineer`、`Sr. ML Eng`） |
| `linkedin_url`、`twitter_username` | 社交链接 | PII，可能为空 |
| `course_join_question` | 报名时对课程自定义问题的回答 | 只有课程在报名页设置了问题才有内容；没设置时整列为空 |
| `enrolled_at` | 报名时间 | 带时区 |
| `source` | 报名来源 | Maven 的界面字符串，例如付费报名与免费报名（`Enrolled for free`，常见于转期或赠课）分开标注 |

**做法。** 先按第 1 节导出目标班期，然后在本地读 CSV，只取 `company`、`job_title`、`source`、`enrolled_at`、`course_join_question` 这几列做汇总，不读也不打印姓名、邮箱和社交链接：

```bash
python3 - <<'PY'
import csv, collections
rows = list(csv.DictReader(open("<PRIVATE_DIR>/students-<cohort>.csv", encoding="utf-8")))
print("enrolled:", len(rows))
print("missing job_title:", sum(not r["job_title"].strip() for r in rows))
print(collections.Counter(r["source"] for r in rows))
for r in rows:
    print(r["job_title"] or "-", "|", r["company"] or "-", "|", r["enrolled_at"][:10])
PY
```

虚构输出示例：

```text
enrolled: 3
missing job_title: 1
Counter({'Payment started': 2, 'Enrolled for free': 1})
Marketing Manager | Example Corp | 2026-01-05
Analyst | Sample Analytics | 2025-12-20
- | - | 2026-01-08
```

**隐私。** 职位和公司组合起来，在小班期里足以认出具体的人，所以和姓名、邮箱一样只留在私有目录。给用户汇报时只报按角色归类后的分布（如「3 位工程、1 位市场」），不要逐行列出公司加职位，更不要和姓名放在一起。公开文档与测试一律用虚构示例。
