#!/usr/bin/env python3
"""检查报告 HTML 内嵌 SVG 的两类图形缺陷（零 token 自检，代替截图肉眼检查）：
1. 文字被线/路径穿过或贴得过近（<5px 记 WARN，穿过记 FAIL）
2. 文字超出 viewBox 被裁切（FAIL）
3. 文字压在实心色块上（深底压深字，渲染出来读不清）（FAIL）
4. 文字压文字（两个标签互相覆盖）（FAIL）
5. marker 箭头 id 全文件重复（SVG id 是文档级的，重名会让箭头引用错图）（FAIL）

用法: python3 check_svg_overlap.py <报告.html> [更多.html ...]
退出码: 有 FAIL 时为 1。文字宽度按 CJK≈1em、ASCII≈0.55em 估算，个别 WARN 需人工复核。
"""
import re, sys, math

WARN_GAP = 5.0

def char_w(ch, fs):
    o = ord(ch)
    if o > 127: return fs * 1.0
    if ch == ' ': return fs * 0.3
    return fs * 0.55

def text_bbox(x, y, fs, anchor, s):
    w = sum(char_w(c, fs) for c in s)
    if anchor == 'middle': x -= w / 2
    elif anchor == 'end': x -= w
    return (x, y - 0.78 * fs, x + w, y + 0.22 * fs)  # (x1,y1,x2,y2)

def attr(tag, name, default=None):
    m = re.search(rf'{name}="([^"]*)"', tag)
    return m.group(1) if m else default

def sample_path(d, n=28):
    """采样绝对坐标路径 M/L/Q/C/H/V 上的点。"""
    pts, cur = [], (0.0, 0.0)
    toks = re.findall(r'([MLQCHVZmlqchvz])|(-?\d+\.?\d*)', d)
    seq, nums = [], []
    for cmd, num in toks:
        if cmd: seq.append((cmd, nums := []))
        else: nums.append(float(num))
    for cmd, ns in seq:
        C = cmd.upper()
        if C == 'M' and len(ns) >= 2: cur = (ns[0], ns[1]); pts.append(cur)
        elif C == 'L':
            for i in range(0, len(ns) - 1, 2):
                p = (ns[i], ns[i+1])
                for t in range(1, n): pts.append((cur[0]+(p[0]-cur[0])*t/n, cur[1]+(p[1]-cur[1])*t/n))
                cur = p; pts.append(cur)
        elif C == 'H' and ns:
            p = (ns[-1], cur[1])
            for t in range(1, n): pts.append((cur[0]+(p[0]-cur[0])*t/n, cur[1]))
            cur = p; pts.append(cur)
        elif C == 'V' and ns:
            p = (cur[0], ns[-1])
            for t in range(1, n): pts.append((cur[0], cur[1]+(p[1]-cur[1])*t/n))
            cur = p; pts.append(cur)
        elif C == 'Q':
            for i in range(0, len(ns) - 3, 4):
                c1, p = (ns[i], ns[i+1]), (ns[i+2], ns[i+3])
                for t in [j/n for j in range(1, n+1)]:
                    u = 1 - t
                    pts.append((u*u*cur[0]+2*u*t*c1[0]+t*t*p[0], u*u*cur[1]+2*u*t*c1[1]+t*t*p[1]))
                cur = p
        elif C == 'C':
            for i in range(0, len(ns) - 5, 6):
                c1, c2, p = (ns[i], ns[i+1]), (ns[i+2], ns[i+3]), (ns[i+4], ns[i+5])
                for t in [j/n for j in range(1, n+1)]:
                    u = 1 - t
                    pts.append((u**3*cur[0]+3*u*u*t*c1[0]+3*u*t*t*c2[0]+t**3*p[0],
                                u**3*cur[1]+3*u*u*t*c1[1]+3*u*t*t*c2[1]+t**3*p[1]))
                cur = p
    return pts

def dist_to_bbox(px, py, b):
    dx = max(b[0] - px, 0, px - b[2]); dy = max(b[1] - py, 0, py - b[3])
    return math.hypot(dx, dy)

def check_file(path):
    html = open(path, encoding='utf-8').read()
    issues = []
    for si, m in enumerate(re.finditer(r'<svg\b[^>]*>.*?</svg>', html, re.S)):
        svg = m.group(0)
        label = attr(svg[:svg.index('>')+1], 'aria-label', f'svg#{si+1}')
        vb = attr(svg[:svg.index('>')+1], 'viewBox', '0 0 99999 99999').split()
        vw, vh = float(vb[2]), float(vb[3])
        body = re.sub(r'<defs>.*?</defs>', '', svg, flags=re.S)
        texts, text_tags = [], []
        for t in re.finditer(r'<text\b([^>]*)>(.*?)</text>', body, re.S):
            tag, inner = t.group(1), re.sub(r'<[^>]+>', '', t.group(2)).strip()
            if not inner or 'transform' in tag: continue
            fs = float(attr(tag, 'font-size', '16'))
            bb = text_bbox(float(attr(tag, 'x', '0')), float(attr(tag, 'y', '0')),
                           fs, attr(tag, 'text-anchor', 'start'), inner)
            texts.append((inner, bb)); text_tags.append(tag)
            if bb[0] < -1 or bb[1] < -1 or bb[2] > vw + 1 or bb[3] > vh + 1:
                issues.append(('FAIL', label, f'文字超出画布: "{inner[:22]}" bbox={tuple(round(v) for v in bb)} viewBox={vw:.0f}x{vh:.0f}'))
        segs = []  # (desc, points)
        for l in re.finditer(r'<line\b[^>]*/?>', body):
            tag = l.group(0)
            x1, y1 = float(attr(tag, 'x1', '0')), float(attr(tag, 'y1', '0'))
            x2, y2 = float(attr(tag, 'x2', '0')), float(attr(tag, 'y2', '0'))
            n = 24
            segs.append((f'line({x1:.0f},{y1:.0f}→{x2:.0f},{y2:.0f})',
                         [(x1+(x2-x1)*t/n, y1+(y2-y1)*t/n) for t in range(n+1)]))
        for p in re.finditer(r'<path\b[^>]*/?>', body):
            tag = p.group(0)
            if attr(tag, 'fill', 'none') not in ('none', None): continue  # 实心小箭头等跳过
            d = attr(tag, 'd', '')
            if d: segs.append((f'path[{d[:26]}…]', sample_path(d)))
        for txt, bb in texts:
            worst = None
            for desc, pts in segs:
                for px, py in pts:
                    dd = dist_to_bbox(px, py, bb)
                    if worst is None or dd < worst[0]: worst = (dd, desc)
            if worst and worst[0] == 0:
                issues.append(('FAIL', label, f'线穿文字: "{txt[:22]}" 被 {worst[1]} 穿过'))
            elif worst and worst[0] < WARN_GAP:
                issues.append(('WARN', label, f'线贴文字(间距{worst[0]:.1f}px): "{txt[:22]}" 近 {worst[1]}'))
        # 文字压实心块（深底上压深字，渲染出来根本读不清；线检查和文字检查都抓不到）
        solids = []
        for tag in re.findall(r'<rect\b[^>]*>', body):
            if 'fill="var(--accent)"' not in tag:
                continue
            try:
                rx, ry = float(attr(tag, 'x', 0)), float(attr(tag, 'y', 0))
                rw, rh = float(attr(tag, 'width', 0)), float(attr(tag, 'height', 0))
            except (TypeError, ValueError):
                continue
            solids.append((rx, ry, rx + rw, ry + rh))
        for (txt, bb), tag in zip(texts, text_tags):
            # 块内的白字/浅色字是正常的，只查深色字压深色块
            if any(k in tag for k in ('--surface', '--gold-soft', '#fff', '#ffffff')):
                continue
            for r in solids:
                ox = min(bb[2], r[2]) - max(bb[0], r[0])
                oy = min(bb[3], r[3]) - max(bb[1], r[1])
                if ox > 1 and oy > 1:
                    issues.append(('FAIL', label,
                                   f'文字压实心块: "{txt[:18]}" 压在深色块上 {ox:.0f}×{oy:.0f}px，读不清'))
                    break
        # 文字压文字（两块标签互相覆盖，肉眼一看就糊，但线检查抓不到）
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                (t1, b1), (t2, b2) = texts[i], texts[j]
                ox = min(b1[2], b2[2]) - max(b1[0], b2[0])
                oy = min(b1[3], b2[3]) - max(b1[1], b2[1])
                if ox > 1 and oy > 1:   # 留 1px 容差，避免相邻行误报
                    issues.append(('FAIL', label,
                                   f'文字压文字: "{t1[:16]}" 与 "{t2[:16]}" 重叠 {ox:.0f}×{oy:.0f}px'))
    # marker id 全文件唯一（SVG id 是文档级的；两图重名，后图箭头会引用错/丢）
    marker_ids = re.findall(r'<marker\b[^>]*\bid="([^"]+)"', html)
    dup = sorted({m for m in marker_ids if marker_ids.count(m) > 1})
    if dup:
        issues.append(('FAIL', '全文件',
                       f'marker id 重复 {dup}——SVG id 文档级，各图箭头要用 arr/arrg/fa/pa 等区分'))
    return issues

def main(paths):
    fail = False
    for f in paths:
        issues = check_file(f)
        name = f.split('/')[-1]
        if not issues:
            print(f'✓ {name}: 无问题'); continue
        print(f'✗ {name}: {len(issues)} 处')
        for lv, label, msg in issues:
            print(f'  [{lv}] {label} — {msg}')
            fail |= (lv == 'FAIL')
    return 1 if fail else 0

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
