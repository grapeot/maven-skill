# Promo Code 管理界面参考

本文档记录 2026-10-05 对 Maven 课程设置页 Promo Code（折扣码）区块的观察与一次经授权的真实创建验证，供 Agent 在协助创建、核对或整理折扣码时参考。以下是对当时页面的观察，不是 Maven 的公开接口契约；页面改版后应以实际 DOM 为准，并同步修订本文档。

**示例声明**：本文出现的组织标识（`acme`）、课程 slug（`demo-course`）、推广码（`FRIENDS50`）、减免额度（`$100`、`25%`）与班期 id（`?cohort=42`）**全部是虚构占位符**，与任何真实课程、真实推广码或真实营收无关。真实推广码、额度与兑换次数属于业务数据，不得复制进公开文档。

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
| Code | `input[name="code"]` | 折扣码文本。**只允许字母、数字和连字符 `-`**（实测：含下划线 `_` 会被拒，错误文案 `Promo code can only contain letters, numbers, and hyphens`）。无 `maxlength`、无 `placeholder`、无 `required` 属性；唯一性由页面/服务端校验 |
| Amount off | `input[name="amount_off"]` | 固定金额减免。输入框是空 `text`。**实测输入不带 `$` 的整数即可**；表格**显示**格式为 `$` 前缀 + 千分位逗号（虚构示例 `$100`）。与 Percent off 二选一 |
| Percent off | `input[name="percent_off"]` | 百分比减免。输入框同样是空 `text`；**实测输入不带 `%` 的数字**即可；表格**显示**格式为 `N%`（虚构示例 `25%`）。与 Amount off 二选一 |
| 提交 | `button`，文本 `Create promo code` | 在表单内，`type=button`（由 JS 处理提交），当前未禁用。不是区块标题 `Create a promo code` |

创建规则（来自 Maven 帮助中心《Discount code strategies》，是文章结论，不是本页点击实测）：先接入 Stripe 并设好价格，否则 Settings 不显示创建入口；金额减免或百分比减免**二选一**；不支持 100% off 的折扣码（学生无法用它免费报名，应改为手动免费导入学员，手动导入同样属于业务写入）；折扣码是课程级、可删除或暂停（pause）。

两个金额输入框在 HTML 层都可编辑，页面脚本是否会在填写一个时清空另一个，未测。表单中间以文本 `OR` 分隔，但 HTML 层不阻止同时填写，业务上须自行只填其一。

---

## 3. 已有推广码表格

表头：`Code` / `Amount off` / `Percent off` / `Redemptions` / `Actions`。空单元格以 `-` 占位；兑换次数是正整数或 `-`（**实测新建行初值为 `-`**，不是 `0`）。

`Actions` 列每行有**三个纯图标按钮**（无文字、无 `aria-label`、无 `title`，真实 hover 也不弹 tooltip）。按 Maven 帮助中心描述，可在此处「复制分享链接（🔗）、暂停（pause）、删除（delete）」，帮助中心截图上的默认顺序是链接、暂停、删除。但本页中间那枚按钮的 SVG 路径在多行间不稳定，且没有点击验证，因此本文档**不把图标的位置或路径当作操作契约**，Agent 不能按名称或图标路径去点这些按钮。

> 由于按钮无语义标签，需要复制链接、暂停或删除时应转交人类；若确需 Agent 协助，也必须先由人类在页面上确认按钮身份，且不替代暂停/删除的业务授权。

---

## 4. 行为与坑点

1. **创建入口始终可见**：只要课程已接入 Stripe 并设好价格，Promo codes 区块与创建表单就常驻 Settings 页，无需先点某个开关。
2. **Code 只接受字母、数字、连字符**：含下划线的代码会被客户端校验拒绝，内联提示 `Promo code can only contain letters, numbers, and hyphens`，**且不发出任何请求**——表单看起来只是「点了没反应」。输入前先确认代码只由 `[A-Za-z0-9-]` 组成。这是已实测的一种具体拒绝形态，不代表所有「点击无效」都是这个原因。
3. **校验不通过时不一定有弹窗**：已观察到校验失败只以内联文字出现在 Code 字段附近，无对话框、无可辨识的 toast。因此**不能靠「有没有弹窗」判断成败**；判断成败必须回到表格核对新行并刷新复验（见下方流程）。
4. **金额字段是受控输入**：`code` / `amount_off` / `percent_off` 都由 React 组件状态驱动。正常 `fill()` 或逐字符输入通常会带上 `input` 事件并被 React 接收；但若脚本填完后点击无效、组件状态仍为空，可用原生 setter（`Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set`）+ 派发 `input` / `change` 事件强制写入。先确认 DOM `value` 与组件状态一致再提交。
5. **新建行 Redemptions 初值是 `-`**，不是 `0`；`Amount off` 显示为 `$` 前缀（填整数 `100` 显示 `$100`）。
6. **这是创建按钮，未授权不要点**：点击 `Create promo code` 会真实创建折扣码。已实测**没有二次确认对话框**，创建成功后随即出现在表格中（刷新后仍在）。仍属业务写入，必须先获人类对具体动作的单独授权。
7. **两个「Create」文本要区分**：区块标题是 `Create a promo code`，提交按钮是 `Create promo code`。定位提交按钮时应按精确文本匹配，避免误点到标题。
8. **金额与百分比的互斥是业务规则**：HTML 层不阻止同时填写两个字段，但语义上只能用一个；创建时应只填其一并把另一个留空。
9. **分享链接不在表格文字里**：Maven 帮助中心说创建后用 link 图标复制分享链接，截图里的形态是落地页加 `?promoCode=` 一类参数。页面上的 `Direct payment link` 区块是**班期 join 链接**（形态 `/<cohort-id>/join?seats=1`），查询参数里没有 promo，不能拿来拼折扣链接。`Marketing` 区另有一个文本为 `Create share link`、字段为 `email` 的控件，与折扣分享链接无关，不要点。
10. **折扣与分成**：Maven 的 10% 分成基于学生实付价格（含折扣后），不是原价，折扣码不改变分成比例（帮助中心结论）。

### 已实测的创建流程（2026-10-05，经用户授权）

1. 打开课程 Settings 页（带 `?cohort=<id>` 亦可，Promo 表不随班期变）。
2. 等到 `input[name="code"]` 出现。
3. 写入 `code`（只含 `[A-Za-z0-9-]`）与 `amount_off`（纯数字，不带 `$`）或 `percent_off`（纯数字，不带 `%`），另一个留空；确认 DOM `value` 与组件状态一致。
4. 点击精确文本为 `Create promo code` 的按钮。
5. **验收**：到表格查找该 Code，确认额度与预期一致；再 `reload` 页面复验该行仍在。新建行的 `Redemptions` 显示为 `-`。表格行数会随创建增加，但不要把它当作唯一判据。
6. 失败排查：若点击后表格无新行，检查 Code 是否含下划线/特殊字符，并读取 Code 字段附近的内联提示。

> 已实测：先提交一个含下划线的代码被内联校验拒绝（无网络请求），换成连字符版本后创建成功；表格出现新行、`reload` 后仍在。本文档不记录真实代码名与真实额度。

---

## 5. 写入边界与授权

本仓库 CLI 目前**只读**，没有创建、暂停或删除 promo code 的命令，也不应据本文档擅自新增写操作。

- 任何 promo code 的创建、暂停、删除都是**业务写入**，必须先获得人类用户对**具体动作**的单独显式授权；本文档、页面操作步骤与「先读参考文档」本身都不构成授权。
- 只读核对（导航到 Settings、读取 Promo codes 区块与表格）无需授权。读取到的真实推广码与额度属业务数据，只留在本机私有数据目录，不得写入公开文档或提交进仓库。
- 只读核对应沿用在独立工作标签页中执行、`finally` 关闭的生命周期（与 CLI 的 `work_page` 一致），不要用 `page goto` 驱动用户正在浏览的标签页。
- 与 Lightning Lesson Settings 中「关联已有 promo code」不是同一个界面：那是 lesson 级关联设置，这里是课程级创建表单，注意区分。

---

## 6. 临时探测脚本卫生

- 临时 Playwright 探测脚本若中途崩溃，会在用户浏览器中留下打开的工作标签页。
- 始终在 `try` / `finally` 中关闭自己打开的工作标签页（与 CLI 的 `work_page` 生命周期一致），只关闭自己创建的页面，不触碰用户原有标签页。
- 探测产生的页面文本与 JSON 可能含真实推广码与营收数字，只能留在私有数据目录（默认 `.local/`），不得进入公开仓库。
