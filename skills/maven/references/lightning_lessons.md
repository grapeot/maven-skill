# Lightning Lesson 管理界面参考

本文档记录 2026-10-03 对 Maven Lightning Lesson（免费短时直播课）管理界面的人工观察结果，供 Agent 在协助准备、检查或复盘 Lightning Lesson 时参考。以下内容是对当时页面的观察，不是 Maven 的公开接口契约；页面改版后应以实际 DOM 为准，并同步修订本文档。

示例中的组织标识（`acme`）与课程 ID（`abc123`）均为虚拟占位符。

---

## 1. 导航与页面结构

- **入口**：Dashboard → Lightning Lessons，对应管理路径 `/<org>/admin/lightning-lessons`（例如 `https://maven.com/acme/admin/lightning-lessons`）。组织标识应从账号菜单与 Dashboard 动态发现，不要硬编码。
- **列表分组**：列表页按 `DRAFTS (N)` / `UPCOMING (N)` / `PAST (N)` 三组展示。每张卡片链接到 `/<org>/admin/lightning-lessons/<id>`。
- **编辑器**：`/<org>/admin/lightning-lessons/<id>/edit`，为单页表单，所有字段在同一页面内。
- **已发布课程**：除编辑器外还有三个标签页，`?tab=overview`、`?tab=signups`、`?tab=settings`。

---

## 2. 编辑器字段契约

| 字段 | 控件与约束 |
|---|---|
| Title | 文本输入，≤ 60 字符；页面显示 `N/60` 计数 |
| Date | react-datepicker；日期格的 `aria-label` 形如 `Choose Wednesday, October 21st, 2026` |
| Start time | react-select；输入如 `11:00 AM` 后点击下拉选项 |
| 时区 | 固定为 `America/Los_Angeles`（页面提示 “All times are in America/Los_Angeles”） |
| Duration | 30 分钟至 3 小时，15 分钟步进，默认 30 分钟 |
| Link | 唯一选项为 “Create a Zoom meeting”；点击一次即创建一个真实的 Zoom 会议 |
| Learning outcomes | 每条标题 ≤ 60、描述 ≤ 120；页面提示三条最有说服力。**新建草稿只有一条 outcome**，需点 “Add outcome” 追加。折叠状态的 outcome 卡片需先点开，输入框才可见；输入框 `name` 为 `learning_outcomes.N.title` 与 `learning_outcomes.N.description` |
| Why this topic matters | textarea，`name=topic_desc`，≤ 450 字符 |
| Instructors | 最多 4 位。姓名 ≤ 30（`input name=name`）；mini bio ≤ 80（`textarea name=title`）；头像 ≥ 800×800 且 < 5MB，经 Filestack 选择器上传（设置文件 input 后依次点击选择器的 “Save”（裁剪）与 “Upload”）；LinkedIn / X / 自定义链接各 ≤ 80，可选；品牌标签 ≤ 80 与最多 5 个 BrandFetch logo，可选；“More about you” ≤ 800，为 ProseMirror contenteditable |
| Social share | 自动生成分享图，或上传自定义图片 |

---

## 3. 行为与坑点

1. **创建无确认**：点击 “Create a Lightning Lesson” 会立即创建一份新草稿，没有确认对话框。
2. **没有 “Save draft” 按钮，字段自动保存**：在编辑器中输入即写入，打字本身就是一次业务写操作。
3. **完成度与错误提示**：页头显示 `N% Complete` 与 `Review N errors`。全部完成后页头只剩 Preview 与 Publish。
4. **硬性发布阻断项是事件链接**：缺少链接时提示 “Add an event link before publishing.”。
5. **自动添加讲师**：新草稿会自动加入一条与组织 expert profile 同步的讲师条目。该 profile 可能是机构而非个人，必填的 mini bio / full bio 可能为空，社交链接也可能与本课无关，需人工核对。
6. **删除讲师立即生效**：“Delete instructor” 没有确认对话框，点击即删除。
7. **发布需审核**：Publish 后由 Maven 审核，大约每个工作日处理一次。
8. **推广节奏与到场率**：根据 Maven 帮助中心，建议提前 2–3 周开始推广，预期约 20% 的报名者会现场参加。参考 [Guide to successfully market your Lightning Lesson](https://help.maven.com/en/articles/9269114-guide-to-successfully-market-your-lightning-lesson) 与 [Lesson prep checklist](https://help.maven.com/en/articles/9621198-lesson-prep-checklist)。

### 已发布课程的标签页

- **Settings**：Product connection（活动结束后报名者自动加入所关联课程的 waitlist）、promo code（折扣码）、Marketplace 可见性。
- **Overview**：时间线（推广、准备、直播、复盘各阶段的待办与指南），以及 `N watched the recording after the live lesson.` 回放观看人数。
- **Signups**：报名者列表。
- 管理界面**没有**现场到场人数统计。

---

## 4. 安全边界

- 以上均为观察记录；`maven-skill` CLI 保持只读，不实现任何编辑器写入。
- 编辑器中的任何写操作（**包括仅仅输入文字**，因为字段自动保存）都属于业务写入，必须先获得人类用户的单独显式授权。
- Publish、Create a Zoom meeting、创建 promo code、发送邮件始终是人类操作，Agent 不代为执行。
- 只读观察时也要避免点击 “Create a Lightning Lesson”“Delete instructor”“Add outcome” 等会立即产生写入的控件。

---

## 5. 临时探测脚本卫生

- 临时 Playwright 探测脚本若中途崩溃，会在用户浏览器中留下打开的工作标签页。
- 始终在 `try` / `finally` 中关闭自己打开的工作标签页（与 CLI 的 `work_page` 生命周期一致），只关闭自己创建的页面，不触碰用户原有标签页。
- 探测产生的截图、页面文本与 JSON 可能含真实学员或讲师信息，只能留在私有数据目录（默认 `.local/`），不得进入公开仓库。
