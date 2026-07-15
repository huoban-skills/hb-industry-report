#!/usr/bin/env python3
"""把报告 figures/ 下的 SVG 导成飞书插图用的 3200px 宽 PNG。

用法：
    python3 scripts/export_png.py <行业名>/<报告.html>

输出到报告同级的 figures-png/。每张图固定宽 3200px，高度按 SVG viewBox
等比计算，并裁掉 Quick Look 生成的透明方形留白。仅依赖 macOS 自带的
qlmanage 与 sips。
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile


WIDTH = 3200


def svg_size(path):
    head = open(path, encoding='utf-8').read(4096)
    match = re.search(r'viewBox=["\']\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)', head)
    if not match:
        raise ValueError('缺少有效 viewBox')
    width, height = map(float, match.groups())
    if width <= 0 or height <= 0:
        raise ValueError('viewBox 宽高必须大于 0')
    return width, height


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True)


def export_one(svg_path, output_dir):
    svg_width, svg_height = svg_size(svg_path)
    target_height = round(WIDTH * svg_height / svg_width)
    preview_size = max(WIDTH, target_height)

    with tempfile.TemporaryDirectory(prefix='hb-report-png-') as temp_dir:
        run('qlmanage', '-t', '-s', str(preview_size), '-o', temp_dir, svg_path)
        previews = [
            os.path.join(temp_dir, name)
            for name in os.listdir(temp_dir)
            if name.lower().endswith('.png')
        ]
        if len(previews) != 1:
            raise RuntimeError(f'Quick Look 应生成 1 张 PNG，实际 {len(previews)} 张')

        output_path = os.path.join(
            output_dir, os.path.splitext(os.path.basename(svg_path))[0] + '.png'
        )
        run(
            'sips', '--cropToHeightWidth', str(target_height), str(WIDTH),
            previews[0], '--out', output_path,
        )
        info = run('sips', '-g', 'pixelWidth', '-g', 'pixelHeight', output_path).stdout
        actual_width = re.search(r'pixelWidth:\s*(\d+)', info)
        actual_height = re.search(r'pixelHeight:\s*(\d+)', info)
        if not actual_width or int(actual_width.group(1)) != WIDTH:
            raise RuntimeError(f'导出宽度不是 {WIDTH}px：{output_path}')
        return output_path, int(actual_height.group(1))


def main(html_path):
    for command in ('qlmanage', 'sips'):
        if not shutil.which(command):
            print(f'FAIL 缺少 macOS 命令：{command}', file=sys.stderr)
            return 2

    report_dir = os.path.dirname(os.path.abspath(html_path))
    figure_dir = os.path.join(report_dir, 'figures')
    output_dir = os.path.join(report_dir, 'figures-png')
    if not os.path.isfile(html_path):
        print(f'FAIL 报告不存在：{html_path}', file=sys.stderr)
        return 2
    if not os.path.isdir(figure_dir):
        print(f'FAIL figures/ 不存在；请先运行 finalize.py：{figure_dir}', file=sys.stderr)
        return 2

    svgs = sorted(
        os.path.join(figure_dir, name)
        for name in os.listdir(figure_dir)
        if name.lower().endswith('.svg')
    )
    if not svgs:
        print(f'FAIL figures/ 中没有 SVG：{figure_dir}', file=sys.stderr)
        return 2

    os.makedirs(output_dir, exist_ok=True)
    for name in os.listdir(output_dir):
        if name.lower().endswith('.png'):
            os.remove(os.path.join(output_dir, name))

    try:
        for svg_path in svgs:
            output_path, height = export_one(svg_path, output_dir)
            print(f'PASS {os.path.basename(output_path)}：{WIDTH}×{height}px')
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'FAIL {exc}', file=sys.stderr)
        return 1

    print(f'\n已导出 {len(svgs)} 张飞书插图：{output_dir}')
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
