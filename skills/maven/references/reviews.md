# 课程评价参考 (`reviews list` / `reviews surveys`)

本文档记录两个只读评价命令的用法、数据来源、页面观察契约、隐私边界与已知坑点。两个命令都不输入文字、不发布、不回复评价，所有点击都经过共享点击守卫。

---

## 1. 命令用法

```bash
# 公开落地页上的学员评价与讲师精选 testimonial（无需登录，但仍走同一个 CDP 浏览器）
maven-skill reviews list --course https://maven.com/<school>/<course>

# 也接受课程管理页 URL，自动换算为公开落地页
maven-skill reviews list --course <COURSE_ADMIN_URL>

# 讲师后台 Surveys 页：各班期 post-course survey 的平均分与回复数（只输出聚合）
maven-skill reviews surveys --course <COURSE_ADMIN_URL>

# 另外把各班期问卷原始回复 CSV 下载到私有目录（可用 --cohort 限定单个班期）
maven-skill reviews surveys --course <COURSE_ADMIN_URL> --download [--cohort "Cohort 3"|3] [--output-dir <DIR>]
```

`--cohort` 接受页面上的班期标签（如 `Cohort 3`、`Self-paced cohort`，大小写不敏感）或纯数字（等价于 `Cohort N`）。`--output-dir` 只能与 `--download` 一起用。

---

## 2. `reviews list`：公开落地页

### 数据来源

| 字段 | 来源 |
|---|---|
| 评价卡片（姓名、班期标签、头衔·公司、日期、正文） | 页面渲染出的 `Alumni reviews` 卡片；点击 `Show more reviews` 后在右侧抽屉中逐页加载 |
| 首页评价的数值评分、班期名（如 `Cohort 3`）、ISO 时间 | 页面内嵌 `__NEXT_DATA__` 的 `courseReviews`（只含第一页） |
| 其余评价的评分 | 卡片上的 5 个星标图标：实心 = 1，半星 = 0.5，空心 = 0 |
| 课程总评分 | 内嵌 `ratingSummary`（`sum_ratings` / `num_ratings`），并与页面文字 `X.X (N ratings)` 交叉核对 |
| 讲师精选 testimonial | 内嵌 `landingPage.profile.content.testimonials`（`is_visible` 为假时不输出） |

内嵌数据只读取需要的字段；`user_id`、头像、学校与支付相关字段不进入输出。

### 输出语义

- 每条评价：`source=public_review`、`name`（页面显示名）、`anonymous`、`headline`（`Title · Company`，页面没有时为 `null`）、`cohort`（页面标签，如 `Jul 2026 Live cohort`）、`cohort_name`（仅内嵌数据覆盖的评价有）、`date`（ISO 日期）、`rating`（0–5）、`rating_source`（`embedded_data` / `star_icons`）、`text`（全文，按段落规范空白）。
- 每条 testimonial：`source=public_testimonial`、`name`、`headline`、`text`；没有评分和日期。
- `rating_summary.average` 是所有评分的平均（含无文字的评分）；`listed_reviews_average` 只是列出评价的平均，两者不同是正常的。
- `completeness.status=complete` 要求：解析条数 ≥ 内嵌 `metadata.total`、没有无法解析的卡片、抽屉里不再有 `Show more reviews`。否则为 `partial`。

### 页面观察契约与坑点

1. **评分存储为 0–10，显示为 5 星**。内嵌 `rating=9` 对应 4.5 星，总评分同理（`sum_ratings / num_ratings / 2`）。页面文字四舍五入到一位小数（如 4.96 显示为 `5.0`），所以以内嵌数据为准，页面文字只做交叉核对。
2. **评分数 ≥ 文字评价数**。只打分不写评价的学员计入 `N ratings`，但不出现在评价列表；`metadata.total` 是文字评价数。
3. **分页是抽屉**。落地页只渲染第一页（6 条）。第一次点击 `Show more reviews` 打开右侧抽屉（`role=dialog`），抽屉内还有自己的 `Show more reviews`，每次追加一页，直到按钮消失。抽屉里的卡片是全集，命令读抽屉而不是落地页。
4. **星标三种形态**：实心星（标准路径、`fill=currentColor`）、半星（另一条路径、`fill-rule=evenodd`）、空心星（标准路径、`fill=#FFFFFF`）。三者颜色 class 相同，不能靠颜色区分，必须按路径属性判断；任何一个图标无法识别时该条评分为 `null`。
5. **`Read more` 只是 CSS 截断**。全文已经在 DOM 中，命令读取文本节点，不点击 `Read more`。
6. **匿名评价**：内嵌数据中 `is_anonymous=true` 时，命令丢弃姓名与头衔，`anonymous=true`。
7. 页面若重定向到别的地址（例如自定义落地页），命令报错，不读取错误页面。

---

## 3. `reviews surveys`：讲师后台 post-course survey

### 导航

从课程管理页的 `Surveys` 导航链接动态进入（`<course>/surveys?cohort=…`），不硬编码路径。需要已登录的持久 profile。

### 页面结构

- 顶部 `Course interest survey`（报名前问卷）：不是课程评价，命令跳过并计入 `skipped_cards`。
- `Post-course survey` 区块：`Average rating for N cohorts X.XX / 5`，以及每个班期一张卡片：班期标签、`Completed <date>`（或尚未结束时的 `Reminder email will send on …`）、平均分 `X / 5`、`Share` 按钮与 `N responses` 按钮（无回复时为禁用的 `No responses yet`）。
- 平均分已由 Maven 归一化到 5 分制。

### 下载语义

- **`N responses` 按钮直接触发 CSV 下载**，不打开对话框。命令只在 `--download` 时点击它，点击前核对按钮所在卡片的班期标签与目标一致。`Share`、`Edit` 等控件从不点击。
- 文件默认写入 `<data-dir>/downloads/survey-<course>-<cohort>-<UTC时间戳>.csv`，权限 `0600`，同名拒绝覆盖；收据写入 `<data-dir>/receipts/survey-export-*.json`。**不更新 `receipts/latest.json`**——那是 `students export` 的指针，下游流程依赖它。
- 校验：非 HTML、表头无重复、恰好一个评分列（列名含 `rate` / `rating`）、评分为 0–5 的数字、行数等于按钮上的回复数。失败时删除已下载文件。
- 已观察到的列：`Cohort`、学员姓名/头衔/公司/邮箱、`How would you rate this course?`、`Leave a public review`、`Write a private note`。不同班期的问卷模板可能不同（列集合会变），命令按列名模式定位评分、公开评价与私下留言列，不依赖固定列序。

### 隐私边界

问卷 CSV 含学员姓名、邮箱与私下留言，只保存在私有数据目录。stdout 只输出每个班期的标签、日期、平均分、回复数，以及下载后的聚合：行数、评分直方图与均值、写了公开评价/私下留言的人数、列名、SHA-256 与文件路径。不得把 CSV 内容、学员姓名或私下留言复制进公开仓库、公开文档或日志。

`Leave a public review` 列中的文字与公开落地页上的评价是同一来源（学员填写时选择公开）；公开展示的版本以 `reviews list` 为准。

---

## 4. 两个命令的关系

- `reviews list` 的 `rating_summary.ratings_count` 应等于 `reviews surveys` 的 `total_responses`，`reviews list` 的评价条数应等于各班期 CSV 中 `public_reviews` 之和。二者对不上时，先确认是否有班期问卷尚在进行中或有评价被隐藏。
- 只需要公开口碑素材时用 `reviews list`；需要按班期看评分分布或私下反馈时用 `reviews surveys --download`，并在本地读取私有 CSV。
