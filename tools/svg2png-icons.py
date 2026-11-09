#!/usr/bin/python3
"""Render all SVG symbols as small square PNG icons, e.g. for taginfo.json

Output goes to taginfo/icons/, mirroring the symbols/ directory tree, so
symbols/buoy/can/outer.svg becomes taginfo/icons/buoy/can/outer.png

Like Mapnik, the drawing's bounding box is used rather than the SVG
document size: each icon is cropped to what is actually drawn, scaled to
fit keeping its aspect ratio, and centred on a transparent canvas.

PNGs that are newer than their SVG are not regenerated, use --force
to render all of them anyway.

Requires rsvg-convert (librsvg2-bin) and ImageMagick.

usage: svg2png-icons.py [--force] [--size N]"""
import argparse
import os
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from svgbbox import bbox  # noqa: E402

NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
for prefix, uri in (('xlink', 'http://www.w3.org/1999/xlink'),
                    ('inkscape', 'http://www.inkscape.org/namespaces/inkscape'),
                    ('sodipodi', 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd')):
    ET.register_namespace(prefix, uri)

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / 'symbols'
DST = ROOT / 'taginfo' / 'icons'


def cropped_svg(svg, size):
    """SVG source with viewBox set to the drawing's bounding box"""
    tree = ET.parse(svg)
    root = tree.getroot()
    try:
        x0, y0, x1, y1 = bbox(svg)
    except (ValueError, IndexError) as e:
        # fall back to the document page as rsvg would render it
        print('%s: %s, using document size' % (svg, e), file=sys.stderr)
        return ET.tostring(root)
    w, h = x1 - x0, y1 - y0
    # make the box square around the drawing's centre
    d = max(w, h)
    x0 -= (d - w) / 2
    y0 -= (d - h) / 2
    root.set('viewBox', '%g %g %g %g' % (x0, y0, d, d))
    root.set('width', str(size))
    root.set('height', str(size))
    root.set('preserveAspectRatio', 'xMidYMid meet')
    return ET.tostring(root)


def render(svg, png, size):
    rsvg = subprocess.run(['rsvg-convert', '-w', str(size), '-h', str(size)],
                          input=cropped_svg(svg, size),
                          capture_output=True, check=True)
    subprocess.run(['convert', '-', '-background', 'none',
                    '-gravity', 'center', '-extent', '%dx%d' % (size, size),
                    '-strip', 'PNG32:%s' % png],
                   input=rsvg.stdout, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--size', type=int, default=16)
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    # remove icons whose SVG is gone, e.g. after renaming a symbol
    for png in sorted(DST.rglob('*.png')):
        if not (SRC / png.relative_to(DST)).with_suffix('.svg').exists():
            png.unlink()
            print('removed', png.relative_to(ROOT))

    for svg in sorted(SRC.rglob('*.svg')):
        png = (DST / svg.relative_to(SRC)).with_suffix('.png')
        if not args.force and png.exists() \
                and png.stat().st_mtime > svg.stat().st_mtime:
            continue
        png.parent.mkdir(parents=True, exist_ok=True)
        render(svg, png, args.size)
        print(png.relative_to(ROOT))


if __name__ == '__main__':
    main()
