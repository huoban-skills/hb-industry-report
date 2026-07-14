# 同步到飞书文档（可选交付通道）

用户给出飞书文档链接/token、要求"传上去、图也一起传"时走本流程。**先读 `lark-doc` skill 的 SKILL.md 与 `lark-doc-xml.md`**（XML 语法以那边为准），本文只讲这份报告特有的转换规则和坑。

前提：`lark-cli auth status --json --verify` 显示 user 身份 valid。

## 三步

### 1. HTML → 飞书 XML，整篇写入

用 bs4 遍历 `.wrap` 的子元素做块级映射，**图的位置先留占位段落**（`<p>FIGPLACEHOLDER1</p>`），图注单独存一份纯文本备用：

| HTML | 飞书 XML |
|---|---|
| `header.cover` | `<title>` + 副题段落 |
| `.abstract` | `<h1>摘要</h1>` + 段落 |
| `nav.toc` | **丢弃**（飞书有自带大纲侧栏） |
| `section` 的 `h2` | `<h1>一、行业背景</h1>`（章序号要补上，HTML 里它在 `.eyebrow` 里） |
| `.lede` | `<p><em>…</em></p>` |
| `h3` / `h4` / `h5` | `<h2>` / `<h3>` / **加粗段落行**（`h5` 不该占标题层级，否则大纲全是"谁在参与"） |
| `.callout` | `<callout emoji="💡" background-color="light-blue" border-color="blue">` |
| `.warnbox` | `<callout emoji="❗" background-color="light-red" border-color="red">` |
| `.stats` | 表格（指标｜数值） |
| `dl.glossary` | 表格（术语｜解释） |
| `.flow` | 一行 `A → B → C` |
| `a.term` | **纯文本**（页内锚点到飞书失效） |
| `figure` | 占位段落，见下 |
| `footer` | `<hr/>` + 段落 |

注意附录的分类标题（HTML 里是 `h4`）要落成 `<h2>`，否则从 `<h1>附录` 直接跳 `<h3>`。

写入：`lark-cli docs +update --doc <token> --command overwrite --content @doc.xml --as user`
（`--content @file` 只吃 **cwd 下的相对路径**，先 cd 到工作目录。）

### 2. SVG → 2x PNG

飞书文档不吃内嵌 SVG，把每张图单独渲染成 PNG（无头 Chrome 截图 SVG 外框元素，2 倍分辨率）。

### 3. 插图 → 搬到位 → 清占位

```bash
lark-cli docs +media-insert --doc <token> --file fig_export_1.png \
  --align center --width 720 --caption "图 1 · ……" --as user
```

`media-insert` 只能插到**文档末尾**，所以：全部插完 → `docs +fetch --detail with-ids` 拿到每张图的 block_id 和每个占位段落的 block_id → `block_move_after` 把图搬到对应占位段落之后 → `block_delete` 批量删掉占位段落。

## 坑（都踩过）

- **`media-insert` 的进度日志会混进 stdout**，`json.load(stdout)` 必然失败。要么按行找 JSON 起始位置，要么先落盘再解析——**不要因为解析失败就重试命令**，图其实已经插进去了，重试会插重复。
- `block_move_after` 偶尔返回成功但没真移动。搬完必须 `fetch` 回来核对每张图的落位，发现没动就用标题的 block_id 当锚点再搬一次。
- 图注里的 `"` 和换行会被转义成 `&#34;` `&#xA;`，属正常。
- `overwrite` 会清空文档重写，**只对空文档或用户明确同意重建的文档用**。
