#!/usr/bin/python3
"""Rewrite SVGs to a SIZE x SIZE document using one common scale factor for
all files so relative symbol sizes are kept.

By default each drawing is centred on its bounding box. With --anchor-bottom
the bottom centre of the original document (e.g. the foot of a top mark's
stalk) is put at the bottom centre of the new document instead. As Mapnik
centres markers on the bounding box of what is drawn, not on the document,
an invisible rect covering the whole document is added in that case so
that the document frame defines the marker's position.

usage: svg-resize.py [--anchor-bottom] SIZE file.svg...
       (files are rewritten in place)"""
import re
import sys
import xml.etree.ElementTree as ET

from svgbbox import bbox

NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)


def doc_size(root):
    vb = root.get('viewBox')
    if vb:
        x, y, w, h = [float(v) for v in vb.replace(',', ' ').split()]
        return x, y, w, h
    num = lambda v: float(re.match(r'[-+]?[\d.]+', v).group())
    return 0.0, 0.0, num(root.get('width')), num(root.get('height'))


args = sys.argv[1:]
anchor_bottom = args[0] == '--anchor-bottom'
if anchor_bottom:
    args = args[1:]
size = float(args[0])
files = args[1:]
boxes = {f: bbox(f) for f in files}

if anchor_bottom:
    anchors = {}
    for f in files:
        x, y, w, h = doc_size(ET.parse(f).getroot())
        anchors[f] = (x + w / 2, y + h)
    # everything must fit above the anchor and within size/2 to either side
    up = max(anchors[f][1] - y0 for f, (x0, y0, x1, y1) in boxes.items())
    side = max(max(anchors[f][0] - x0, x1 - anchors[f][0])
               for f, (x0, y0, x1, y1) in boxes.items())
    k = min(size / up, size / 2 / side)
else:
    k = size / max(max(x1 - x0, y1 - y0) for x0, y0, x1, y1 in boxes.values())
print('common scale %.6f' % k)

for f, (x0, y0, x1, y1) in boxes.items():
    root = ET.parse(f).getroot()
    if anchor_bottom:
        tx = size / 2 - k * anchors[f][0]
        ty = size - k * anchors[f][1]
    else:
        tx = size / 2 - k * (x0 + x1) / 2
        ty = size / 2 - k * (y0 + y1) / 2
    g = ET.Element('{%s}g' % NS, transform='matrix(%.6f,0,0,%.6f,%.4f,%.4f)' % (k, k, tx, ty))
    for ch in list(root):
        root.remove(ch)
        g.append(ch)
    root.attrib.clear()
    root.set('version', '1.1')
    root.set('width', '%g' % size)
    root.set('height', '%g' % size)
    root.set('viewBox', '0 0 %g %g' % (size, size))
    if anchor_bottom:
        ET.SubElement(root, '{%s}rect' % NS, width='%g' % size, height='%g' % size,
                      fill='none', stroke='none')
    root.append(g)
    ET.indent(root, space='  ')
    ET.ElementTree(root).write(f, encoding='UTF-8', xml_declaration=True)
    print('%-20s %.2fx%.2f px' % (f.split('/')[-1], k * (x1 - x0), k * (y1 - y0)))
