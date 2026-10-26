#!/usr/bin/python3
"""Compute the visual bounding box of simple SVG files (path/rect/circle/
ellipse/line/polyline/polygon with nested <g> transforms), including stroke
width. Curves and arcs are sampled, which is accurate enough for layout.

usage: svgbbox.py file.svg..."""
import math
import re
import sys
import xml.etree.ElementTree as ET


def mat_mul(a, b):
    # 2x3 affine matrices (a, b, c, d, e, f) as in SVG matrix()
    return (a[0]*b[0] + a[2]*b[1], a[1]*b[0] + a[3]*b[1],
            a[0]*b[2] + a[2]*b[3], a[1]*b[2] + a[3]*b[3],
            a[0]*b[4] + a[2]*b[5] + a[4], a[1]*b[4] + a[3]*b[5] + a[5])


IDENT = (1, 0, 0, 1, 0, 0)


def parse_transform(s):
    m = IDENT
    for name, args in re.findall(r'(\w+)\s*\(([^)]*)\)', s or ''):
        v = [float(x) for x in re.findall(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', args)]
        if name == 'matrix':
            t = tuple(v)
        elif name == 'translate':
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == 'scale':
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == 'rotate':
            r = math.radians(v[0])
            t = (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)
            if len(v) == 3:
                t = mat_mul(mat_mul((1, 0, 0, 1, v[1], v[2]), t), (1, 0, 0, 1, -v[1], -v[2]))
        else:
            raise ValueError('unsupported transform ' + name)
        m = mat_mul(m, t)
    return m


def apply(m, x, y):
    return m[0]*x + m[2]*y + m[4], m[1]*x + m[3]*y + m[5]


def style_of(el, inherited):
    st = dict(inherited)
    for k in ('fill', 'stroke', 'stroke-width'):
        if el.get(k) is not None:
            st[k] = el.get(k)
    for decl in (el.get('style') or '').split(';'):
        if ':' in decl:
            k, v = decl.split(':', 1)
            st[k.strip()] = v.strip()
    return st


NUM = r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'


def path_points(d, steps=24):
    toks = re.findall(r'[MmLlHhVvCcSsQqTtAaZz]|' + NUM, d)
    pts, i = [], 0
    x = y = sx = sy = 0.0
    cmd = None
    last_ctrl = None

    def num():
        nonlocal i
        v = float(toks[i]); i += 1
        return v

    while i < len(toks):
        if re.match(r'[A-Za-z]', toks[i]):
            cmd = toks[i]; i += 1
            if cmd in 'Zz':
                x, y = sx, sy
                pts.append((x, y))
                last_ctrl = None
                continue
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if c == 'M':
            x, y = ox + num(), oy + num()
            sx, sy = x, y
            pts.append((x, y))
            cmd = 'l' if rel else 'L'
            last_ctrl = None
        elif c == 'L':
            x, y = ox + num(), oy + num(); pts.append((x, y)); last_ctrl = None
        elif c == 'H':
            x = ox + num(); pts.append((x, y)); last_ctrl = None
        elif c == 'V':
            y = (y if rel else 0.0) + num(); pts.append((x, y)); last_ctrl = None
        elif c in 'CS':
            if c == 'C':
                x1, y1 = ox + num(), oy + num()
            else:
                x1, y1 = (2*x - last_ctrl[0], 2*y - last_ctrl[1]) if last_ctrl else (x, y)
            x2, y2 = ox + num(), oy + num()
            x3, y3 = ox + num(), oy + num()
            for k in range(1, steps + 1):
                t = k / steps; u = 1 - t
                pts.append((u**3*x + 3*u*u*t*x1 + 3*u*t*t*x2 + t**3*x3,
                            u**3*y + 3*u*u*t*y1 + 3*u*t*t*y2 + t**3*y3))
            last_ctrl = (x2, y2); x, y = x3, y3
        elif c in 'QT':
            if c == 'Q':
                x1, y1 = ox + num(), oy + num()
            else:
                x1, y1 = (2*x - last_ctrl[0], 2*y - last_ctrl[1]) if last_ctrl else (x, y)
            x2, y2 = ox + num(), oy + num()
            for k in range(1, steps + 1):
                t = k / steps; u = 1 - t
                pts.append((u*u*x + 2*u*t*x1 + t*t*x2, u*u*y + 2*u*t*y1 + t*t*y2))
            last_ctrl = (x1, y1); x, y = x2, y2
        elif c == 'A':
            rx, ry, phi = abs(num()), abs(num()), math.radians(num())
            fa, fs = num(), num()
            x2, y2 = ox + num(), oy + num()
            pts.extend(arc_points(x, y, rx, ry, phi, fa, fs, x2, y2, steps))
            x, y = x2, y2; last_ctrl = None
    return pts


def arc_points(x1, y1, rx, ry, phi, fa, fs, x2, y2, steps):
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp*dx + sp*dy, -sp*dx + cp*dy
    lam = (x1p/rx)**2 + (y1p/ry)**2
    if lam > 1:
        rx *= math.sqrt(lam); ry *= math.sqrt(lam)
    num_ = rx*rx*ry*ry - rx*rx*y1p*y1p - ry*ry*x1p*x1p
    den = rx*rx*y1p*y1p + ry*ry*x1p*x1p
    co = math.sqrt(max(0, num_ / den)) if den else 0
    if fa == fs:
        co = -co
    cxp, cyp = co*rx*y1p/ry, -co*ry*x1p/rx
    cx = cp*cxp - sp*cyp + (x1 + x2)/2
    cy = sp*cxp + cp*cyp + (y1 + y2)/2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux*vy - uy*vx, ux*vx + uy*vy)
        return a
    t1 = ang(1, 0, (x1p - cxp)/rx, (y1p - cyp)/ry)
    dt = ang((x1p - cxp)/rx, (y1p - cyp)/ry, (-x1p - cxp)/rx, (-y1p - cyp)/ry)
    if not fs and dt > 0:
        dt -= 2*math.pi
    elif fs and dt < 0:
        dt += 2*math.pi
    out = []
    for k in range(1, steps*2 + 1):
        t = t1 + dt*k/(steps*2)
        out.append((cx + rx*math.cos(t)*cp - ry*math.sin(t)*sp,
                    cy + rx*math.cos(t)*sp + ry*math.sin(t)*cp))
    return out


def shape_points(el, tag):
    f = lambda k, dflt=0.0: float(el.get(k, dflt))
    if tag == 'path':
        return path_points(el.get('d', ''))
    if tag == 'rect':
        x, y, w, h = f('x'), f('y'), f('width'), f('height')
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    if tag in ('circle', 'ellipse'):
        cx, cy = f('cx'), f('cy')
        rx = f('r') if tag == 'circle' else f('rx')
        ry = f('r') if tag == 'circle' else f('ry')
        return [(cx + rx*math.cos(a/32*2*math.pi), cy + ry*math.sin(a/32*2*math.pi)) for a in range(32)]
    if tag == 'line':
        return [(f('x1'), f('y1')), (f('x2'), f('y2'))]
    if tag in ('polyline', 'polygon'):
        v = [float(n) for n in re.findall(NUM, el.get('points', ''))]
        return list(zip(v[0::2], v[1::2]))
    return []


SKIP = {'defs', 'metadata', 'title', 'desc', 'namedview', 'guide'}


def walk(el, m, st, acc):
    tag = el.tag.split('}')[-1]
    if tag in SKIP:
        return
    if tag in ('symbol', 'use'):
        raise ValueError('<%s> found' % tag)
    m = mat_mul(m, parse_transform(el.get('transform')))
    st = style_of(el, st)
    if st.get('display') == 'none':
        return
    pts = shape_points(el, tag)
    has_stroke = st.get('stroke', 'none') not in ('none', '')
    if st.get('fill') in ('none', '') and not has_stroke:
        pts = []    # invisible, e.g. a frame rect
    if pts:
        sw = float(re.match(NUM, st.get('stroke-width', '1')).group()) if has_stroke else 0.0
        scale = math.sqrt(abs(m[0]*m[3] - m[1]*m[2]))
        hw = sw / 2 * scale
        for px, py in pts:
            X, Y = apply(m, px, py)
            acc.append((X - hw, Y - hw)); acc.append((X + hw, Y + hw))
    for ch in el:
        walk(ch, m, st, acc)


def bbox(path):
    root = ET.parse(path).getroot()
    acc = []
    walk(root, IDENT, {'fill': '#000000'}, acc)
    xs = [p[0] for p in acc]; ys = [p[1] for p in acc]
    return min(xs), min(ys), max(xs), max(ys)


if __name__ == '__main__':
    for p in sys.argv[1:]:
        x0, y0, x1, y1 = bbox(p)
        print('%-20s x %7.2f..%7.2f  y %7.2f..%7.2f  w %6.2f h %6.2f' % (p.split('/')[-1], x0, x1, y0, y1, x1 - x0, y1 - y0))
