# Promo Code 管理界面参考

本文档记录 2026-10-05 对 Maven 课程设置页 Promo Code（折扣码）区块的观察与一次经授权的真实创建验证，以及 2026-10-07 对 Actions 列按钮身份的只读核对，供 Agent 在协助创建、核对或整理折扣码时参考。以下是对当时页面的观察，不是 Maven 的公开接口契约；页面改版后应以实际 DOM 为准，并同步修订本文档。

**示例声明**：本文出现的组织标识（`acme`）、课程 slug（`demo-course`）、推广码（`FRIENDS50`、`friends50`、`SPRING25`）、减免额度与价格（`$100`、`25%`、`$1,000`、`$900`）与班期 id（`?cohort=42`）**全部是虚构占位符**，与任何真实课程、真实推广码或真实营收无关。真实推广码、额度与兑换次数属于业务数据，不得复制进公开文档。

---

## 1. 入口与页面结构

- **入口**：课程管理页 → `Settings`，路径 `/<org>/admin/courses/<course-slug>/settings`，例如 `https://maven.com/acme/admin/courses/demo-course/settings`。
- **带班期参数**：进入 Settings 时页面通常自动带上 `?cohort=<id>`（例如 `?cohort=42`）。Cohort 区块会按该参数显示对应班期；Promo codes 表格不随班期变化。
- **区块顺序**（Settings 内）：General（Names and URLs、Cohort info）→ Payments（Stripe、Pricing、Direct payment link、**Promo codes**）→ Applications → Marketing → Visibility → Community → Integrations → Course staff。
- **Promo codes 区块**：位于 Payments 组内，标题为 `Promo codes`，说明文字为 “Offer discounts through promo codes, and copy links to share with your students. Codes apply to all cohorts in this course, live and self-paced.”。区块内先是一个**内联创建表单**，其下是**已有推广码表格**。
- **作用域**：折扣码属于**课程**而非班期；代码对同一课程的所有班期（含 live 与 self-paced）生效。管理页表格不随班期切换而改变，支持这一结论；学生在另一个班期结账时是否真能核销，本文档未实测。

---

## 2. 创建表单契约

区块文本为 `Create a promo code` → `Code` / `Amount off` `OR` `Percent off` → 按钮 `Create promo code`。表单是一个常驻的原生 `<form action="#">`，不在弹窗里：

| 元素 | 定位 | 说明 |
|---|---|---|
| Code | `input[name="code"]` | 折扣码文本。**只允许字母、数字和连字符 `-`，不接受下划线 `_`**（实测：含 `_` 被拒，错误文案 `Promo code can only contain letters, numbers, and hyphens`）。构造代码前先自检 `^[A-Za-z0-9-]+$`。无 `maxlength`、无 `placeholder`、无 `required` 属性；唯一性由页面/服务端校验 |
| Amount off | `input[name="amount_off"]` | 固定金额减免。输入框是空 `text`。**实测输入不带 `$` 的整数即可**；表格**显示**格式为 `$` 前缀 + 千分位逗号（虚构示例 `$100`）。与 Percent off 二选一 |
| Percent off | `input[name="percent_off"]` | 百分比减免。输入框同样是空 `text`；**实测输入不带 `%` 的数字**即可；表格**显示**格式为 `N%`（虚构示例 `25%`）。与 Amount off 二选一 |
| 提交 | `button`，文本 `Create promo code` | 在表单内，`type=button`（由 JS 处理提交），当前未禁用。不是区块标题 `Create a promo code` |

创建规则（来自 Maven 帮助中心《Discount code strategies》，是文章结论，不是本页点击实测）：先接入 Stripe 并设好价格，否则 Settings 不显示创建入口；金额减免或百分比减免**二选一**；不支持 100% off 的折扣码（学生无法用它免费报名，应改为手动免费导入学员，手动导入同样属于业务写入）；折扣码是课程级、可删除或暂停（pause）。

两个金额输入框在 HTML 层都可编辑，页面脚本是否会在填写一个时清空另一个，未测。表单中间以文本 `OR` 分隔，但 HTML 层不阻止同时填写，业务上须自行只填其一。

---

## 3. 已有推广码表格

表头：`Code` / `Amount off` / `Percent off` / `Redemptions` / `Actions`。空单元格以 `-` 占位；兑换次数是正整数或 `-`（**实测新建行初值为 `-`**，不是 `0`）。表格是 Settings 页上唯一一张 `thead` 里有精确文本 `Code` 的 `h5` 的 `<table>`。

### 3.1 Actions 列的三个按钮

每行 Actions 单元格里有三个纯图标 `<button>`：没有文字、`aria-label`、`title` 或 `data-*` 属性，真实 hover 也不弹 tooltip。2026-10-07 只读核对（读 DOM、React 绑定的 onClick 源码与组件源码，未点击）确认了三者的身份：

| 默认位置 | 作用 | 图标 | 点击行为 |
|---|---|---|---|
| 1 | 复制分享链接 | `viewBox 0 0 24 24`，两段描边弧线（链接） | 复制 `?promoCode=<CODE>` 链接 |
| 2（`class="pl-1"`） | **暂停/恢复切换** | 激活的码：双竖条（暂停）；已暂停的码：右指三角形（恢复）。`viewBox 0 0 16 16`，单条 `fill-rule=evenodd` 路径 | 单击即生效，**没有确认框**；toast 为 `Paused <CODE>` / `Restarted <CODE>` |
| 3 | 删除 | `viewBox 0 0 16 16`，多条描边路径（垃圾桶） | 先弹浏览器原生 `confirm("Are you sure you want to delete <CODE>?")`，确认后删除 |

- **中间按钮是切换，不是单向暂停**。它对当前状态取反（`active: !active`）。误点即生效；重复点击会把刚暂停的码重新激活。因此结果不确定时**不要重试**，先刷新读回状态。
- **暂停的行整行置灰**：`tr` 带 class `text-gray-400`，激活的行没有这个 class。
- **图标随状态切换**：激活时显示双竖条，暂停后显示三角形。早先「中间按钮 SVG 路径在多行间不稳定」的说法是误读：路径不是随机变化，而是反映状态；当时又按码文本去配对数据，被同名重复码错位放大。按行配对后，图标、置灰与页面数据中的 `active` 在全表逐行一致。
- 暂停与恢复走同一个更新请求，只改 `active` 字段；删除是另一个请求。Maven 没有折扣码过期设置（表单只有三个字段，数据对象也没有过期或次数上限字段），帮助中心给出的「过期」做法就是手动暂停或删除。

### 3.2 同名重复码

Maven 允许同名码共存，包括大小写不同的变体（例如 `FRIENDS50` 与 `friends50`，或两条都叫 `FRIENDS50`、一条暂停一条激活）。由此有两条硬规则：

1. **查找必须校验唯一性**：按大小写不敏感比较，命中多于一行就停下，不要「取第一行」。
2. **按行配对数据，不按码文本配对**：页面 React 数据里的码列表与表格行一一对应，必须按行序号对齐并核对每行码文本；按码文本去 `find` 会在重复码上拿到另一行的状态。

### 3.3 识别原则

- 仍然**不能按位置点击**：位置只作为附带记录，不作为判据。
- 识别从「不可识别、转交人类」改为「多证据一致才算识别」。`maven-skill promo-codes locate-pause`（第 5 节）用四项检查识别暂停按钮：图标几何、onClick 源码、另两个按钮的身份、当前状态。
- 识别出按钮**不等于获得暂停授权**。暂停是业务写入，见第 6 节。

### 3.4 暂停是否生效：公开链接验证

用**不带 cookie**的浏览器 context 打开公开落地页 `https://maven.com/<school>/<course>?promoCode=<CODE>`，看报名卡片：

- 激活的码：出现划线原价和折后价（虚构示例：划线 `$1,000`，折后 `$900`）。
- 已暂停的码：与不存在的码一样，只显示原价，没有划线价。

所以暂停前先记录一次「有划线价」的基线，暂停后再打开同一链接确认划线价消失，可以作为独立于管理页的验收。结账页是否也拒绝已暂停的码，本文档未实测。

---

## 4. 行为与坑点

1. **创建入口始终可见**：只要课程已接入 Stripe 并设好价格，Promo codes 区块与创建表单就常驻 Settings 页，无需先点某个开关。
2. **Code 只接受字母、数字、连字符**：含下划线的代码会被客户端校验拒绝，内联提示 `Promo code can only contain letters, numbers, and hyphens`，**且不发出任何请求**——表单看起来只是「点了没反应」。输入前先确认代码只由 `[A-Za-z0-9-]` 组成。这是已实测的一种具体拒绝形态，不代表所有「点击无效」都是这个原因。
3. **校验不通过时不一定有弹窗**：已观察到校验失败只以内联文字出现在 Code 字段附近，无对话框、无可辨识的 toast。因此**不能靠「有没有弹窗」判断成败**；判断成败必须回到表格核对新行并刷新复验（见下方流程）。
4. **金额字段是受控输入**：`code` / `amount_off` / `percent_off` 都由 React 组件状态驱动。正常 `fill()` 或逐字符输入通常会带上 `input` 事件并被 React 接收；但若脚本填完后点击无效、组件状态仍为空，可用原生 setter（`Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set`）+ 派发 `input` / `change` 事件强制写入。先确认 DOM `value` 与组件状态一致再提交。
5. **新建行 Redemptions 初值是 `-`**，不是 `0`；`Amount off` 显示为 `$` 前缀（填整数 `100` 显示 `$100`）。
6. **这是创建按钮，未授权不要点**：点击 `Create promo code` 会真实创建折扣码。已实测**没有二次确认对话框**，创建成功后随即出现在表格中。仍属业务写入，必须先获人类对具体动作的单独授权。**成功必须以读回为准**（见下方验收），不能以「点击了、无报错」判定。
7. **两个「Create」文本要区分**：区块标题是 `Create a promo code`，提交按钮是 `Create promo code`。定位提交按钮时应按精确文本匹配，避免误点到标题。
8. **金额与百分比的互斥是业务规则**：HTML 层不阻止同时填写两个字段，但语义上只能用一个；创建时应只填其一并把另一个留空。
9. **分享链接不在表格文字里**：Maven 帮助中心说创建后用 link 图标复制分享链接。链接格式已实测，见下方「折扣分享链接」一节。页面上的 `Direct payment link` 区块是**班期 join 链接**（形态 `/<cohort-id>/join?seats=1`），查询参数里没有 promo，不能拿来拼折扣链接。`Marketing` 区另有一个文本为 `Create share link`、字段为 `email` 的控件，与折扣分享链接无关，不要点。
10. **折扣与分成**：Maven 的 10% 分成基于学生实付价格（含折扣后），不是原价，折扣码不改变分成比例（帮助中心结论）。

### 折扣分享链接（已实测 2026-10-06，只读）

带折扣的落地页链接格式是：

```
https://maven.com/<school>/<course>?promoCode=<CODE>
```

- **参数名是 `promoCode`，C 大写。** 用未登录的无头浏览器打开，落地页报名卡片显示原价划线和折后价，折扣自动应用，访客不需要手动输码。
- **码值不区分大小写**：同一个码的全大写写法也能生效。
- **这些写法不生效**，页面仍显示原价：`?coupon=`、`?promo=`、`?code=`、`?discount=`、`?promo_code=`。含下划线的码本来也建不出来（见第 2 条），拼进链接自然无效。
- **验收方法**：生成二维码或对外发链接前，用未登录的浏览器打开链接，确认报名卡片上出现划线原价和折后价；不要只凭链接「看起来对」就发出去。
- 这只是读取公开落地页，不涉及任何写入；码本身是否存在、是否已用，以 Settings 页 Promo codes 表格为准（第 3 节）。

### 已实测的创建流程（2026-10-05，经用户授权）

1. 打开课程 Settings 页（带 `?cohort=<id>` 亦可，Promo 表不随班期变）。
2. 等到 `input[name="code"]` 出现。
3. 写入 `code`（只含 `[A-Za-z0-9-]`）与 `amount_off`（纯数字，不带 `$`）或 `percent_off`（纯数字，不带 `%`），另一个留空；确认 DOM `value` 与组件状态一致。
4. 点击精确文本为 `Create promo code` 的按钮。
5. **验收（写入后必须读回）**：点击提交后**不能**以「点击了、无报错、界面有变化」判定成功。必须回到权威视图独立复验——重新 `reload` 页面，在 Promo codes 表格中查找该 Code，确认额度与预期一致、该行确实存在。只有读回确认后才算完成。新建行的 `Redemptions` 显示为 `-`（表格行数会随创建增加，但不要把它当作唯一判据）。
6. 失败排查：若点击后表格无新行，检查 Code 是否含下划线/特殊字符，并读取 Code 字段附近的内联提示。

> 已实测：先提交一个含下划线的代码被内联校验拒绝（无网络请求），换成连字符版本后创建成功；表格出现新行、`reload` 后仍在。本文档不记录真实代码名与真实额度。

---

## 5. 只读 CLI：`promo-codes list` 与 `promo-codes locate-pause`

两个命令都只导航到 `<课程管理页>/settings` 并读取，页面经只读门面访问：只有导航、登记过的只读脚本，以及对单行的滚动、元素截图和测量包围盒。门面没有 click、fill、type、hover、键盘或 locator 接口，模块代码里也没有任何点击调用。命令不点击 Actions 列任何按钮，不在 Settings 页输入任何内容。

`--course` 接受课程管理页 URL（可带 `/settings?cohort=<id>` 等子路径）或 `<school>/<course>`；`list` 还接受裸课程 slug，此时与 `courses list` 一样经账号菜单发现课程（这是首页账号菜单上一次经点击守卫的点击，不在 Settings 页）。`locate-pause` 不接受裸 slug，因此它在整个运行中零点击。

### 5.1 `promo-codes list`

```bash
maven-skill promo-codes list --course https://maven.com/acme/admin/courses/demo-course [--json]
```

逐行输出 code、amount off、percent off、redemptions（页面的 `-` 记为 0）与 status，默认是文本表格，`--json` 输出完整结构。status 由三个独立信号合成：

1. 切换按钮图标的几何形状：两条分开的竖条矩形为激活，右指三角形为暂停（按 SVG 路径几何判别，不比对整串路径常量）；
2. 行是否带 `text-gray-400`；
3. 页面 React 数据里该行的 `active`（可选信号）。它来自压缩后的前端数据，只在按行序号对齐且每行码文本一致时采用；读不到或对不齐时降级（`react_data` 为 `unavailable` / `misaligned`），不报错。

任一信号不一致时该行 status 为 `unknown`。输出还标记大小写不敏感的重复码（每行 `duplicate` 与顶层 `duplicates`）。表头不是 `Code / Amount off / Percent off / Redemptions / Actions`，或页面上这样的表格不止一张时，命令以页面改版为由报错。

### 5.2 `promo-codes locate-pause`

```bash
maven-skill promo-codes locate-pause --course https://maven.com/acme/admin/courses/demo-course \
  --code FRIENDS50 --output-dir .local/pause_check [--json]
```

前置要求：该码在表中大小写不敏感地**恰好出现一次**（不存在或重复都直接报错退出，不写产物），该行 Actions 单元格**恰好 3 个按钮**。在三个按钮里找唯一一个图标为暂停或恢复形状的按钮，然后做四项检查：

| 检查 | 内容 |
|---|---|
| E1 图标 | 目标按钮是双竖条（码已暂停时为三角形） |
| E2 handler | 目标按钮的 React onClick 源码同时含 `active:`、`"Paused"` 字面量与对 `active` 的取反 |
| E3 排他 | 另两个按钮一个是复制链接（源码含 `PromoCodeCopy`）、一个是删除（源码含 `confirm(` 与 `delete`）；读不到源码时退回图标几何（链接 / 垃圾桶），源码与几何矛盾即失败 |
| E4 状态 | 行未置灰，且按行对齐的 React 数据 `active=true` |

判定：

- 四项都通过：`confidence=high`，`verdict=ready_to_pause`。
- E1、E3 通过，E2 或 E4 只是因为读不到 React 数据而缺失（没有失败）：`confidence=medium`，仍为 `ready_to_pause`。
- 码已暂停（三角形、置灰、`active=false` 一致）：`verdict=already_paused`，此时框出的按钮作用是**恢复**，绝不能点；`confidence` 只表示对这颗切换按钮的识别程度。
- 其他情况：`verdict=not_ready`，`confidence=none`，并说明哪一项失败。

产物写入 `--output-dir`（目录 `0700`，文件 `0600`，同名覆盖）：

- `row.png`：该行的元素截图；
- `annotated.png`：在截图上用 PIL 按按钮包围盒画框（不改 DOM），`not_ready` 时不画框；
- `evidence.json`：行 HTML、单元格、三个按钮的属性、SVG 路径、onClick 源码节选、包围盒、四项检查、置信度与公开链接基线。

命令还会新建一个无 cookie 的浏览器 context 打开 `?promoCode=<CODE>` 公开链接，记录报名卡片是否有划线价（`public_link.has_struck_price`），作为暂停前的基线（第 3.4 节）；该检查失败只记为 `checked=false`，不影响判定。退出码：`ready_to_pause` 与 `already_paused` 为 0，`not_ready` 为 3，其他错误为 1。

stdout 与产物含真实码名、额度与兑换次数，属于业务数据，只留在私有目录。

---

## 6. 写入边界与授权

本仓库 CLI 只读：`promo-codes list` 与 `promo-codes locate-pause` 只读取和截图，没有创建、暂停或删除 promo code 的命令，也不应据本文档擅自新增写操作。`locate-pause` 给出 `high` 置信度只说明按钮已被识别，不构成暂停授权。

- 任何 promo code 的创建、暂停、删除都是**业务写入**，必须先获得人类用户对**具体动作**的单独显式授权；本文档、页面操作步骤与「先读参考文档」本身都不构成授权。
- 只读核对（导航到 Settings、读取 Promo codes 区块与表格）无需授权。读取到的真实推广码与额度属业务数据，只留在本机私有数据目录，不得写入公开文档或提交进仓库。
- 只读核对应沿用在独立工作标签页中执行、`finally` 关闭的生命周期（与 CLI 的 `work_page` 一致），不要用 `page goto` 驱动用户正在浏览的标签页。
- 与 Lightning Lesson Settings 中「关联已有 promo code」不是同一个界面：那是 lesson 级关联设置，这里是课程级创建表单，注意区分。

---

## 7. 临时探测脚本卫生

- 临时 Playwright 探测脚本若中途崩溃，会在用户浏览器中留下打开的工作标签页。
- 始终在 `try` / `finally` 中关闭自己打开的工作标签页（与 CLI 的 `work_page` 生命周期一致），只关闭自己创建的页面，不触碰用户原有标签页。
- 探测产生的页面文本与 JSON 可能含真实推广码与营收数字，只能留在私有数据目录（默认 `.local/`），不得进入公开仓库。
