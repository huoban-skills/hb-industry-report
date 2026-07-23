#!/usr/bin/env python3
"""报告内容自检（零 token，代替人肉 grep 自检清单）。

把 SKILL.md 自检清单里「机器能判的」那部分变成可执行的质量闸：
交付（导 PDF / 同步飞书）之前必须 FAIL=0。

用法：
    python3 scripts/check_report.py <报告.html> [更多报告.html ...]

退出码：有 FAIL 返回 1，否则 0（可接进 CI / 交付前置条件）。

检查项（FAIL = 必须修，WARN = 人工判断）：
  1. 章节骨架        2.3 业务协作链 / 2.4 资金流转 / 3.3 方案建议     FAIL
  2. 图号连续        <b>图 N</b> 从 1 起、无断号重号                   FAIL
  3. 图注完整        每个 <figure> 都有带图号的 figcaption             FAIL
  4. 术语死链        正文 a.term 的 href 在附录找不到词条              FAIL
  5. 术语孤儿        附录有词条、正文从没链过去                        FAIL
  6. 图内抽象词      SVG 文字里出现抽象黑名单词                        FAIL
  7. SVG 硬编码色    fill/stroke 写死颜色而非 var(--x)                 FAIL
  8. SVG 未定义变量  图内 var(--x) 未在 :root 声明                     FAIL
  9. 正文抽象词      正文/表格里的黑名单词（可能误报，人工看）          WARN
 10. 图解元话语      "如图所示""把图 N 走一遍"这类废话                 WARN
 11. 系统维度用语    按钮/字段/自动化/导入导出（行业固有词会误报）      WARN
 12. 业务块五段      3.2 每个 .block 固定五个 h5 齐全                    FAIL
"""
import re
import sys
import html as H

ABSTRACT = ["要素", "交付", "输入", "输出", "职责", "赋能", "协同", "资源整合"]
REQUIRED_H5 = ["这个环节在做什么", "子流程", "谁在参与", "业务特征", "痛点"]
SYSTEM_WORDS = ["按钮", "自动化", "字段", "导入导出", "导 Excel", "软件系统"]
META_TALK = [r"如图所示", r"把图\s*\d+\s*走一遍", r"对照图", r"见上图", r"如下图"]

REQUIRED_SECTIONS = [
    (r"2\.3\s*上下游业务协作链", "2.3 上下游业务协作链（旧名「资金上下游与利益分配」已废弃）"),
    (r"2\.4\s*资金流转与利益分配", "2.4 资金流转与利益分配（2.3/2.4 必须分立成两节）"),
    (r"3\.3\s*方案建议", "3.3 方案建议（旧名「方案切入视角」已废弃）"),
]


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s)


def check(path):
    src = open(path, encoding="utf-8").read()
    body = src.split("</head>", 1)[-1]
    fails, warns = [], []

    # --- 1. 章节骨架 ---
    heads = " ".join(re.findall(r"<h3[^>]*>(.*?)</h3>", body, re.S))
    for pat, desc in REQUIRED_SECTIONS:
        if not re.search(pat, heads):
            fails.append(f"[章节骨架] 缺 {desc}")

    # --- 2/3. 图号与图注 ---
    figures = re.findall(r"<figure\b.*?</figure>", body, re.S)
    nums = []
    for i, fig in enumerate(figures, 1):
        cap = re.search(r"<figcaption[^>]*>(.*?)</figcaption>", fig, re.S)
        if not cap:
            fails.append(f"[图注完整] 第 {i} 个 <figure> 没有 figcaption")
            continue
        m = re.search(r"图\s*(\d+)", strip_tags(cap.group(1)))
        if not m:
            fails.append(f"[图注完整] 第 {i} 个图的 figcaption 里没有「图 N」编号")
        else:
            nums.append(int(m.group(1)))
    if nums:
        expect = list(range(1, len(nums) + 1))
        if nums != expect:
            fails.append(f"[图号连续] 图号应为 {expect}，实际 {nums}（断号/重号/乱序）")

    # --- 4/5. 术语链接 ---
    hrefs = set(re.findall(r'<a[^>]*class="term"[^>]*href="#(term-[^"]+)"', body))
    ids = set(re.findall(r'<div[^>]*id="(term-[^"]+)"', body))
    for d in sorted(hrefs - ids):
        fails.append(f"[术语死链] 正文链到 #{d}，附录没有这个词条")
    orphans = sorted(ids - hrefs)
    if orphans:
        fails.append(
            f"[术语孤儿] {len(orphans)} 个词条正文从没链过去："
            + "、".join(o.replace("term-", "") for o in orphans)
        )

    # --- 12. 业务块五段齐全（3.2 每个 .block 固定五个 h5）---
    block_opens = [mo.start() for mo in re.finditer(r'<div[^>]*class="block"[^>]*>', body)]
    if not block_opens:
        warns.append("[业务块] 没找到任何 .block——3.2 分块详解是不是漏了？")
    for k, start in enumerate(block_opens):
        end = block_opens[k + 1] if k + 1 < len(block_opens) else len(body)
        nxt_h3 = re.search(r"<h3\b", body[start:end])   # 最后一块别吞掉 3.3/附录
        if nxt_h3:
            end = start + nxt_h3.start()
        h5s = [strip_tags(t) for t in re.findall(r"<h5[^>]*>(.*?)</h5>", body[start:end], re.S)]
        missing = [r for r in REQUIRED_H5 if not any(r in h for h in h5s)]
        if missing:
            fails.append(
                f"[业务块五段] 第 {k + 1} 个环节缺 {'、'.join(missing)}"
                f"（五段固定：{'/'.join(REQUIRED_H5)}）"
            )

    # --- 5b. div 闭合平衡（callout/warnbox 漏 </div> 会把后文整段吞进样式盒） ---
    nosvg = re.sub(r"<svg\b.*?</svg>", "", body, flags=re.S)
    n_open, n_close = len(re.findall(r"<div\b", nosvg)), nosvg.count("</div>")
    if n_open != n_close:
        # 逐行累计深度，定位第一处「开了 callout/warnbox 却直到下个 h3/figure 还没关」的行
        hint = ""
        depth, opened_at = 0, None
        for ln, line in enumerate(nosvg.split("\n"), 1):
            for m in re.finditer(r"<div\b[^>]*class=\"(callout|warnbox)\"|<div\b|</div>", line):
                t = m.group(0)
                if t == "</div>":
                    depth -= 1
                    if depth <= 0:
                        opened_at = None
                else:
                    depth += 1
                    if 'class="callout"' in t or 'class="warnbox"' in t:
                        opened_at = (ln, t[:40])
            if opened_at and re.search(r"<(h3|figure)\b", line) and ln > opened_at[0]:
                hint = f"；疑似第 {opened_at[0]} 行的 {opened_at[1]}… 未闭合"
                break
        fails.append(f"[div未闭合] <div> {n_open} 个 / </div> {n_close} 个，不配对{hint}——漏 </div> 会把后文吞进 callout/warnbox 样式")

    # --- 6/7/8. SVG 内部 ---
    root_blocks = re.findall(r":root(?:\[[^]]+\])?\s*\{([^{}]*)\}", src, re.S)
    declared_vars = set(re.findall(r"(--[A-Za-z0-9_-]+)\s*:", "\n".join(root_blocks)))
    for svg in re.findall(r"<svg\b.*?</svg>", body, re.S):
        label = re.search(r'aria-label="([^"]*)"', svg)
        tag = (label.group(1)[:24] + "…") if label else "无 aria-label 的图"
        text = H.unescape(" ".join(re.findall(r"<text[^>]*>(.*?)</text>", svg, re.S)))
        text = strip_tags(text)
        hit = [w for w in ABSTRACT if w in text]
        if hit:
            fails.append(f"[图内抽象词] 「{tag}」出现 {'、'.join(hit)}——图内标签必须是具体业务动作")
        hard = re.findall(r'(?:fill|stroke)="(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))"', svg)
        hard = [c for c in hard if c.lower() not in ("#fff", "#ffffff", "none")]
        if hard:
            fails.append(f"[SVG硬编码色] 「{tag}」写死颜色 {sorted(set(hard))[:3]}——应统一用 var(--accent) 等")
        used_vars = set(re.findall(r"var\(\s*(--[A-Za-z0-9_-]+)\s*\)", svg))
        missing_vars = sorted(used_vars - declared_vars)
        if missing_vars:
            fails.append(
                f"[SVG未定义变量] 「{tag}」引用 {'、'.join(missing_vars)}，但未在 :root 声明——浏览器会丢失对应样式"
            )
        # 画布下方大留白：viewBox 高度远超内容实际最低 y（粗估 text/rect/circle/path 端点）
        vb = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
        if vb:
            vh = int(vb.group(2))
            ys = [float(v) for v in re.findall(r'\b(?:y|cy|y1|y2)="([\d.]+)"', svg)]
            ys += [float(v) + float(h) for v, h in re.findall(r'y="([\d.]+)"[^>]*height="([\d.]+)"', svg)]
            ys += [float(v) for p in re.findall(r'\bd="([^"]+)"', svg) for v in re.findall(r"[\s,](\d+(?:\.\d+)?)", p)[1::2]]
            if ys and vh - max(ys) > 80:
                fails.append(f"[SVG下方留白] 「{tag}」viewBox 高 {vh}，内容最低约 y={max(ys):.0f}——画布过高留出大片空白，收窄高度")

    # --- 9/10/11. 正文（WARN） ---
    prose = strip_tags(re.sub(r"<svg\b.*?</svg>", "", body, flags=re.S))
    for w in ABSTRACT:
        n = prose.count(w)
        if n:
            warns.append(f"[正文抽象词] 「{w}」出现 {n} 次——确认是业务实词还是套话")
    for pat in META_TALK:
        if re.search(pat, prose):
            warns.append(f"[图解元话语] 命中 /{pat}/——图后直接讲事，别写「对照图看」")
    for w in SYSTEM_WORDS:
        n = prose.count(w)
        if n:
            warns.append(f"[系统维度用语] 「{w}」出现 {n} 次——报告只写业务，不写系统")

    return fails, warns


def main(paths):
    total_fail = 0
    for p in paths:
        fails, warns = check(p)
        total_fail += len(fails)
        print(f"\n{'='*64}\n{p}")
        for f in fails:
            print(f"  FAIL  {f}")
        for w in warns:
            print(f"  WARN  {w}")
        if not fails:
            print(f"  PASS  无 FAIL（WARN {len(warns)} 项，人工判断）")
    print(f"\n{'='*64}\n总计 FAIL {total_fail} 项。交付前必须清零。")
    return 1 if total_fail else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
