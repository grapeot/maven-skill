# 往班期 Syllabus 里加内容（浏览器写入参考）

本文记录往某个班期的 Syllabus 加模块和 lesson 的做法：可见浏览器里由 agent 操作、页面自己的编辑器和上传通道完成写入，CLI 本身不提供写命令。内容基于 2026-10 的页面观察；按钮文案、节点名和接口随时可能变，动手前先在可见窗口里核对。

## 0. 授权与边界

- **这是业务写入。** 只有用户对「往哪个班期加什么」明确授权后才做；参考文档本身不构成授权。
- **用可见窗口。** `maven-skill session open`（不要换成 headless wrapper），让用户能看到 agent 在做什么。脚本用 CDP 连 `127.0.0.1:<port>` 上的同一个浏览器。
- **绝不用「Import content」。** Syllabus 页右侧的 Import content from other cohorts 会用另一个班期**替换整个 syllabus，并永久删除学员的作业提交和 lesson 完成记录**。往进行中的班期加内容只能手工建模块和 item。新开班期时，在学员入学前从上一期导入才是它的正确用法。
- **只动自己新建的东西。** 已有模块和 item 不改、不删、不挪。

## 1. 先弄清会发生什么

| 事实 | 影响 |
|---|---|
| **没有草稿。** item 没有 Draft/Published 状态，Save changes 之后学员立刻能看到 | 想先搭好再放出，只能先把模块的 Module release date 设到将来，检查完再改回来 |
| **课程落地页展示的是招生中班期的 syllabus** | 模块的 Course landing page visibility 为 Public 时，模块名、描述和每个 item 标题会出现在公开落地页上；Private 则对访客隐藏 lesson 和 project 标题 |
| **内容按班期存** | 加到一期不影响其他期，包括 self-paced 班期 |
| **通知** | 只有设了截止日期（item 的日历按钮）才会在到期前一天邮件提醒没完成的学员；不设就不发。没有「新内容自动通知」，要通知得手动发 broadcast |
| **视频** | 上传上限 2 GB 的 MP4；编辑器里没有字幕入口 |
| **编辑器** | tiptap：段落、标题、列表、引用、代码块、分隔线，**行内代码**（code mark），自有的 `customImage` / `customVideo` / `customFile`；**没有表格**（转成图片） |

## 2. 页面结构

- Syllabus：`<课程管理路径>/cohorts/<slug>/syllabus`。按 Pre-course / Week N / Post-course / Bonus 分组，每组末尾有 Add more（Module / Event）。
- 模块编辑页：`.../syllabus/modules/<module_id>?item=<item_id>`。上方是模块标题、可选描述、Module release date（时钟图标）、Course landing page visibility（眼睛图标）、更多菜单（View as student、Copy student link、Delete module）；下方左侧是 item 列表和 Add item（Lesson / Project / Event），右侧是当前 item：emoji 按钮、标题、正文和工具栏（B I U、两种列表、链接、Image、Video、File；日历是截止日期；更多菜单是 Enable free preview、View as student、Copy student link、Delete）。
- 页面上有四个 ProseMirror：模块标题、模块描述、item 标题（纯文本 schema）、item 正文（含 `customImage` 的那个）。DOM 元素上挂着 tiptap 的 `editor`。

## 3. 建模块

在目标分组点 Add more → Module：出现一个 Module name 输入框（上限 80 字符）和 Save / Cancel。Save 发出 `POST https://api.maven.com/syllabi/<syllabus_id>/module`（`{"module_type": "<分组>", "title": ...}`），模块追加在该分组最后。之后点模块名旁的 Add your first item 进入模块编辑页，页面会自带一个 Untitled lesson。

## 4. 填一个 lesson

1. **新建**：Add item → Lesson（菜单项是 menuitem）。
2. **标题必须用键盘输入。** 对标题编辑器调用 `setContent` 只改显示，保存时不会提交；点进标题编辑器，全选，`keyboard.insert_text(title)`。
3. **emoji**：标题上方的 emoji 按钮要用**鼠标点击**（合成的 `.click()` 打不开选择器）。选择器有 Search 输入框；结果是宽约 40 px、`aria-label` 为 emoji 名字的按钮（分类标签是 30 px），emoji 本身是图片，按钮文字为空。
4. **正文文字**：正文编辑器 `editor.commands.setContent('', true)` 后，用 `insertContentAt(doc.content.size, html)` 逐段插入 HTML。
5. **图片**：把光标放到末尾（`focus('end')`），点工具栏 Image 按钮，接住文件选择器设文件。直接对隐藏的 `input[accept="image/*"]` 设文件不可靠；同一个文件重复选择不会触发 change，每次先把所有 file input 的 value 清空。完成的判据：文档里多一个 `customImage`，`src` 是 http 地址，`isimageuploading` 为**字符串** `"false"`。
6. **视频**：Image 后面那个没有 tooltip 的按钮是 Video，点开后点 Upload video，接住文件选择器。上传走 `POST api.maven.com/assets/video_assets/direct_upload` 到 Mux。完成的判据：`customVideo` 节点 `progresspercentage` 为 100 且有 `video_asset_id`（`src` 一直是 null）。
7. **注意节点是行内的。** `customImage` 和 `customVideo` 放在段落里面，统计要用 `editor.state.doc.descendants`，只看 `getJSON().content` 顶层会数成 0。
8. **规范化排版再保存。** 学员页的段落没有上下间距，空白全靠空段落：一次 `setContent` 整篇放进去的 HTML 段落挤成一片；逐段 `insertContentAt` 时标签之间的换行又会变成空段落，在列表里变成**空的圆点**。保存前按一条规则重建正文：去掉所有空段落和空列表项；文字和图片挤在同一段的拆开，每个图片或视频单独成段；相邻的块之间恰好放一个空段落，图片和紧跟的斜体图注之间不放。做法是在 ProseMirror 里遍历顶层节点，组出新的 Fragment，再用一次 `tr.replaceWith(0, doc.content.size, ...)` 提交；媒体节点原样复用，不会重新上传。
9. **代码块语言。** 编辑器默认语言是 javascript，标成 `text` 或没标语言的代码块会被当成 JavaScript 高亮，普通英文的提示词里会出现彩色关键词。可用语言里有 `plaintext`，把这类代码块的 `language` 改成它；bash、json 等保持原样。
10. **核对后保存。** 图片数、视频数和清单一致才点 Save changes；它发出 `PUT https://api.maven.com/syllabi/<syllabus_id>/modules/<module_uuid>?should_update_module_items=true`，一次提交整个模块（描述和所有 item）。保存后页面会回到 Syllabus 总览，下一个 lesson 要重新打开模块编辑页。

## 5. 坑

| 现象 | 原因 / 对策 |
|---|---|
| 保存后 item 仍叫 Untitled lesson | 标题是用 `setContent` 改的。改用键盘输入。 |
| Save changes 按钮变成转圈，一直不恢复，也没有网络请求 | 页面内部状态卡住（实测常发生在保存后重新打开模块、紧接着填的那个 lesson）。这时内容还没保存：刷新模块页（确认离开）丢弃，再重做这个 lesson。脚本里给每个 lesson 一次「刷新后重试」。 |
| 一次失败后接着跑下一个，结果顺序乱了、出现半成品 lesson | 失败的 lesson 留在页面状态里，会被下一次 Save changes 一起提交。一失败就停下，刷新丢弃，再继续；批量循环要按退出码判断，不能靠 grep 输出。 |
| 只是点开几个 item 看了看，页面就显示 Unsaved changes | 编辑器加载时规范化了内容。不需要保存，刷新丢弃即可，避免误存。 |
| 图片传上去了，统计却是 0 | 节点是行内的，见第 4 节第 7 步。 |
| 等图片上传「完成」一直超时 | `isimageuploading` 存的是字符串 `"false"`，按布尔判断会一直当成在上传。 |
| 删 item 没有确认框 | item 更多菜单里的 Delete 点了就删（保存后生效），删前核对选中的是哪个 item。 |
| 排序错了 | 侧栏可以拖动，但自动化拖动不可靠；删掉排错的 item 再按顺序重建更稳。 |
| 学员页段落挤在一起，或列表里有空的圆点 | 空段落多了或少了。按第 4 节第 8 步重建正文；已经保存的 lesson 也可以单独打开、规范化、再保存。 |
| 提示词代码块里英文单词被染色 | 默认语言是 javascript。改成 `plaintext`（第 4 节第 9 步）。 |

## 6. 交付前核对

- 逐个点开 item：标题、emoji、图片数、视频数、行内代码数和清单一致；然后刷新丢弃点开造成的 Unsaved changes。
- **在学员页逐页看排版**，不能只看编辑器：段落和标题之间有没有空隙、列表里有没有空圆点、纯文本代码块有没有被染色、图片和图注是否连在一起。学员页正文在内部滚动容器里，整页截图截不到，要滚动到具体元素再截。
- 学员视角：`/<school>/<course>/<slug>/home` 能看到模块和 item 数；打开一两个 lesson 看图片、视频、代码块是否正常。
- 告诉用户：模块位置、可见性（落地页是否展示）、是否设了 release date、有没有发通知。
