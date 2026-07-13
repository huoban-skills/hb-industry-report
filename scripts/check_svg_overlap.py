#!/usr/bin/env python3
"""检查报告 HTML 内嵌 SVG 的两类图形缺陷（零 token 自检，代替截图肉眼检查）：
1. 文字被线/路径穿过或贴得过近（<5px 记 WARN，穿过记 FAIL）
2. 文字超出 viewBox 被裁切（FAIL）

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
        texts = []
        for t in re.finditer(r'<text\b([^>]*)>(.*?)</text>', body, re.S):
            tag, inner = t.group(1), re.sub(r'<[^>]+>', '', t.group(2)).strip()
            if not inner or 'transform' in tag: continue
            fs = float(attr(tag, 'font-size', '16'))
            bb = text_bbox(float(attr(tag, 'x', '0')), float(attr(tag, 'y', '0')),
                           fs, attr(tag, 'text-anchor', 'start'), inner)
            texts.append((inner, bb))
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
    return issues

def main():
    fail = False
    for f in sys.argv[1:]:
        issues = check_file(f)
        name = f.split('/')[-1]
        if not issues:
            print(f'✓ {name}: 无问题'); continue
        print(f'✗ {name}: {len(issues)} 处')
        for lv, label, msg in issues:
            print(f'  [{lv}] {label} — {msg}')
            fail |= (lv == 'FAIL')
    sys.exit(1 if fail else 0)

main()
