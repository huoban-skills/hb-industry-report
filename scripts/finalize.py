#!/usr/bin/env python3
"""终稿复检：定稿后、交付前，跑这一个脚本把三件事一次做完。

    python3 scripts/finalize.py <行业名>/<报告.html>

  1. 重导 figures/  —— 把 HTML 里每张内嵌 SVG 重新导成独立 .svg（浅色化 + 补 xmlns）。
                      figures 是内嵌图的派生物，图改过多轮后它就旧了，这里统一对齐。
  2. 内容检查      —— 章节骨架 / 图号 / 图注 / 术语死链与孤儿 / 图内抽象词 / 硬编码色。
  3. 图形检查      —— 线穿文字 / 文字出画布 / 文字叠字 / 文字压色块。

任何一项有 FAIL 就退出码 1、不算过。全绿才能交付（导 PDF / 同步飞书）。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_report import check as content_check          # noqa: E402
from check_svg_overlap import check_file as shape_check   # noqa: E402

# 独立 SVG 脱离 HTML 后 var() 不生效，按浅色主题写死
LIGHT = {
    '--accent': '#1f3a5f', '--accent-soft': '#e8eef5',
    '--gold': '#b08d57', '--gold-soft': '#f7f0e4',
    '--surface': '#ffffff', '--ink': '#1a1a1a', '--ink-soft': '#4a4a4a',
    '--muted': '#8a8a8a', '--line': '#dcdcdc',
}
FIG_NAMES = [('时间轴', '发展时间轴'), ('产品', '产品服务全景'), ('协作链', '业务协作链'),
             ('资金', '资金流转'), ('L1', 'L1业务流程'), ('计息', '多段计息')]


def _to_light(svg):
    for k, v in LIGHT.items():
        svg = svg.replace(f'var({k})', v)
    if 'xmlns=' not in svg:
        svg = svg.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    return svg


def _fig_name(i, svg):
    label = re.search(r'aria-label="([^"]*)"', svg)
    label = label.group(1) if label else ''
    for kw, name in FIG_NAMES:
        if kw in label:
            return f'{i:02d}-{name}'
    return f'{i:02d}-图{i}'


def reexport_figures(html_path):
    body = open(html_path, encoding='utf-8').read().split('</head>', 1)[-1]
    svgs = re.findall(r'<svg\b.*?</svg>', body, re.S)
    figdir = os.path.join(os.path.dirname(html_path) or '.', 'figures')
    os.makedirs(figdir, exist_ok=True)
    for old in os.listdir(figdir):
        if old.endswith('.svg'):
            os.remove(os.path.join(figdir, old))
    for i, svg in enumerate(svgs, 1):
        with open(os.path.join(figdir, _fig_name(i, svg) + '.svg'), 'w', encoding='utf-8') as f:
            f.write(_to_light(svg))
    return len(svgs)


def main(paths):
    total_fail = 0
    for p in paths:
        print(f"\n{'='*64}\n{p}")

        n = reexport_figures(p)
        print(f"  ① figures/ 重导 {n} 张（与报告对齐）")

        fails, warns = content_check(p)
        for f in fails:
            print(f"     FAIL {f}")
        for w in warns:
            print(f"     WARN {w}")
        print(f"  ② 内容检查：{'PASS' if not fails else f'{len(fails)} 项 FAIL'}（WARN {len(warns)}）")

        shape = shape_check(p)
        sfails = [i for i in shape if i[0] == 'FAIL']
        for lv, _lab, msg in shape:
            print(f"     {lv} {msg}")
        print(f"  ③ 图形检查：{'PASS' if not sfails else f'{len(sfails)} 项 FAIL'}")

        total_fail += len(fails) + len(sfails)

    verdict = "全绿，可以交付。" if not total_fail else "清零后才能交付。"
    print(f"\n{'='*64}\n总计 FAIL {total_fail} 项。{verdict}")
    return 1 if total_fail else 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
