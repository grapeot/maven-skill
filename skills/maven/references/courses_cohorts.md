# 课程与班期发现参考 (`courses list` / `cohorts list`)

本文档记录课程列表与班期（Cohort）发现的 CLI 契约与选期规则。命令实现基于页面观察，不逆向私有 API，不硬编码租户或课程路径。

---

## 1. 课程列表 (`courses list`)

```bash
maven-skill courses list
```

- **动态发现**：从 Maven 首页账号菜单动态进入 Dashboard，再进入 Courses 列表；不硬编码组织标识或课程路径。菜单外壳和 Logout 可能先出现，Dashboard 链接随后才插入。命令会等到菜单给出 Dashboard 目的地，而不是在菜单刚打开时读一次就停。目的地优先取文字为 Dashboard 的链接；若已登录菜单里没有这个文字、但只有一个指向 `/{org}/admin` 的链接，用该链接。多个候选不一致时拒绝，不猜测。
- **认证与布局分开报**：跳转登录页，或菜单里是 Log in / Sign up，才是未认证。菜单已打开并有 Logout，却没有 Dashboard 目的地，报布局变化，不报未登录。
- **输出**：页面观察到的课程 URL 与标题列表。支持链接型分页；遇到无法自动遍历的下一页按钮时报告 `completeness.status=partial`。
- **完整性**：必须检查 `completeness`。`partial` 只代表已遍历到的部分，**不等于全量课程**，不得据此断言课程数量或缺失。

---

## 2. 班期列表 (`cohorts list`)

```bash
maven-skill cohorts list --course <COURSE_ADMIN_URL>
```

- **解析**：进入课程概览页，解析观察到的班期卡片，输出 slug、状态、开始日期与页面日期文字。
- **两种页面结构**（都支持）：
  - **2026-10 起**：每张班期卡片本身是一个指向 `<课程管理路径>/cohorts/<slug>` 的链接，卡片文字形如 `Cohort 14 In session Oct 12 – Oct 26, 2026 7 students`（DOM 里年份和人数可能连在一起，解析不受影响）。卡片上不再有 Student home 链接，它挪进了班期自己的管理页；课程级导航也不再有 Students 标签，学员页在每个班期下面（`<课程管理路径>/cohorts/<slug>/students`）。
  - **更早的结构**：卡片里有 Student home 链接和 settings 链接（`?cohort=<slug>`），课程级导航有 Students。
- **slug 交叉核验**：卡片上能读到的 slug 来源（班期管理链接、Student home 链接、settings 链接）只要给出了 slug，就必须一致，不一致即拒绝，不猜测。至少需要一个来源，全部缺失时该卡片无效。
- **状态**：`upcoming`、`in_session`（进行中）、`ended`（已结束）、`self_paced`，都不匹配时为 `scheduled`。
- **完整性**：出现分页控件时报告 `completeness.status=partial`，`pages_visited=1`。
- **导出联动**：班期列表为 `partial` 时，`students export --cohort latest` 拒绝推断 latest；此时应先观察并明确指定实际 slug。

---

## 3. `latest` 选期规则（三条路径）

`latest` 的选择逻辑按以下顺序判定，任何无法唯一确定的路径都拒绝，**绝不按 slug 数字大小猜测**：

1. **恰好一个 Upcoming**：直接选中它。
2. **多个 Upcoming**：按开始日期选最新者。要求所有候选日期含完整年份；缺年份或日期并列时拒绝。
3. **没有 Upcoming**：从状态非 `self_paced` 且带日期的班期中选最新者（通常就是 `in_session` 的那一期）。**注意这条路径可能选中已排期（scheduled）甚至已过去的班期**；同样要求完整年份，缺年份或并列时拒绝。
4. 班期列表为空，或以上都得不到唯一结果：拒绝。

比较日期时一律要求完整年份；只有月份、没有年份时不做排序。

---

## 4. 工作标签页生命周期

- 业务命令在已有持久 context 中开启独立工作标签页，执行完毕或异常退出时都在 `finally` 中关闭，用户原有标签页保持原貌。
- 不使用 `page goto` 驱动用户正在浏览的标签页。
