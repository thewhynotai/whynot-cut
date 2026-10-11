"""Icons for motion videos: the vendored Lucide set (ISC, templates/motion/icons/lucide) turned into After Effects shape
data, plus search for the motion-director and polylines for the animatic.

Shape data per subpath (After Effects convention): {"vertices": [[x, y]], "inTangents": [[dx, dy]],
"outTangents": [[dx, dy]], "closed": bool}; tangents are relative to their vertex. Coordinates are centred on the viewBox
centre and scaled by size / viewBox width, so an icon sits on its layer's origin.
"""
from __future__ import annotations

import difflib
import json
import math
import re
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

from .common import TEMPLATES_DIR

ICON_DIR = TEMPLATES_DIR / "motion" / "icons" / "lucide"
_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
K = 0.5522847498            # cubic approximation of a quarter circle


# --------------------------------------------------------------------------- path parsing
def _scan(d: str):
    """Tokens of a path: command letters and numbers; arc flags may be written without separators ("0120")."""
    i, n = 0, len(d)
    while i < n:
        ch = d[i]
        if ch.isalpha():
            yield ch
            i += 1
        elif ch in " ,\t\r\n":
            i += 1
        else:
            m = _NUM.match(d, i)
            if not m:
                raise ValueError(f"bad path data near {d[i:i + 12]!r}")
            yield m.group(0)
            i = m.end()


class _Sub:
    def __init__(self, p):
        self.nodes = [{"p": p, "in": None, "out": None}]
        self.closed = False

    def line(self, p):
        self.nodes.append({"p": p, "in": None, "out": None})

    def cubic(self, c1, c2, p):
        self.nodes[-1]["out"] = c1
        self.nodes.append({"p": p, "in": c2, "out": None})


def _arc_cubics(p1, rx, ry, phi_deg, fa, fs, p2):
    """SVG arc (endpoint form) -> list of cubic (c1, c2, end) segments, each ≤ 90° (SVG spec F.6.5)."""
    (x1, y1), (x2, y2) = p1, p2
    if (x1, y1) == (x2, y2):
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [(None, None, p2)]
    phi = math.radians(phi_deg)
    cs, sn = math.cos(phi), math.sin(phi)
    dx2, dy2 = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cs * dx2 + sn * dy2, -sn * dx2 + cs * dy2
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    coef = math.sqrt(max(0.0, num / den)) * (-1 if fa == fs else 1)
    cxp, cyp = coef * rx * y1p / ry, -coef * ry * x1p / rx
    cx, cy = cs * cxp - sn * cyp + (x1 + x2) / 2, sn * cxp + cs * cyp + (y1 + y2) / 2

    def ang(u, v):
        return math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1])
    u = ((x1p - cxp) / rx, (y1p - cyp) / ry)
    v = ((-x1p - cxp) / rx, (-y1p - cyp) / ry)
    t1, dt = ang((1, 0), u), ang(u, v)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    n = max(1, math.ceil(abs(dt) / (math.pi / 2) - 1e-9))
    delta = dt / n
    alpha = 4 / 3 * math.tan(delta / 4)

    def pt(t):
        return (cx + rx * math.cos(t) * cs - ry * math.sin(t) * sn, cy + rx * math.cos(t) * sn + ry * math.sin(t) * cs)

    def der(t):
        return (-rx * math.sin(t) * cs - ry * math.cos(t) * sn, -rx * math.sin(t) * sn + ry * math.cos(t) * cs)
    out = []
    for k in range(n):
        a, b = t1 + k * delta, t1 + (k + 1) * delta
        pa, pb, da, db = pt(a), pt(b), der(a), der(b)
        end = p2 if k == n - 1 else pb
        out.append(((pa[0] + alpha * da[0], pa[1] + alpha * da[1]), (pb[0] - alpha * db[0], pb[1] - alpha * db[1]), end))
    return out


def _path(d: str) -> list[_Sub]:
    toks = list(_scan(d))
    subs, cur, start, i = [], None, (0.0, 0.0), 0
    pt = (0.0, 0.0)
    last_c2, last_q, cmd = None, None, None

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    def flag():
        nonlocal i
        t = toks[i]
        if len(t) > 1 and t[0] in "01":      # "011" = flag 0, then "11" stays for the next read
            toks[i] = t[1:]
            return int(t[0])
        i += 1
        return int(float(t))

    def ensure():
        nonlocal cur
        if cur is None or cur.closed:
            cur = _Sub(pt)
            subs.append(cur)
    while i < len(toks):
        if toks[i].isalpha():
            cmd = toks[i]
            i += 1
        elif cmd is None:
            raise ValueError("path data must start with a command")
        rel, C = cmd.islower(), cmd.upper()
        ox, oy = pt if rel else (0.0, 0.0)
        if C == "Z":
            if cur is not None and not cur.closed:
                first, last = cur.nodes[0], cur.nodes[-1]
                if len(cur.nodes) > 1 and math.dist(first["p"], last["p"]) < 1e-9:
                    first["in"] = last["in"]
                    cur.nodes.pop()
                cur.closed = True
            pt, last_c2, last_q = start, None, None
            continue
        if C == "M":
            pt = (ox + num(), oy + num())
            cur = _Sub(pt)
            subs.append(cur)
            start, last_c2, last_q = pt, None, None
            cmd = "l" if rel else "L"          # further pairs are line-tos
            continue
        ensure()
        if C in "LHV":
            if C == "L":
                p = (ox + num(), oy + num())
            elif C == "H":
                p = ((pt[0] if rel else 0.0) + num(), pt[1])
            else:
                p = (pt[0], (pt[1] if rel else 0.0) + num())
            cur.line(p)
            pt, last_c2, last_q = p, None, None
        elif C in "CS":
            if C == "C":
                c1 = (ox + num(), oy + num())
            else:
                c1 = (2 * pt[0] - last_c2[0], 2 * pt[1] - last_c2[1]) if last_c2 else pt
            c2 = (ox + num(), oy + num())
            p = (ox + num(), oy + num())
            cur.cubic(c1, c2, p)
            pt, last_c2, last_q = p, c2, None
        elif C in "QT":
            if C == "Q":
                q = (ox + num(), oy + num())
            else:
                q = (2 * pt[0] - last_q[0], 2 * pt[1] - last_q[1]) if last_q else pt
            p = (ox + num(), oy + num())
            c1 = (pt[0] + 2 / 3 * (q[0] - pt[0]), pt[1] + 2 / 3 * (q[1] - pt[1]))
            c2 = (p[0] + 2 / 3 * (q[0] - p[0]), p[1] + 2 / 3 * (q[1] - p[1]))
            cur.cubic(c1, c2, p)
            pt, last_c2, last_q = p, None, q
        elif C == "A":
            rx, ry, rot = num(), num(), num()
            fa, fs = flag(), flag()
            p = (ox + num(), oy + num())
            for c1, c2, end in _arc_cubics(pt, rx, ry, rot, fa, fs, p):
                if c1 is None:
                    cur.line(end)
                else:
                    cur.cubic(c1, c2, end)
            pt, last_c2, last_q = p, None, None
        else:
            raise ValueError(f"unsupported path command {cmd!r}")
    return subs


def _ellipse(cx, cy, rx, ry) -> _Sub:
    s = _Sub((cx, cy - ry))
    s.nodes[0]["in"], s.nodes[0]["out"] = (cx - K * rx, cy - ry), (cx + K * rx, cy - ry)
    for p, i_, o_ in (((cx + rx, cy), (cx + rx, cy - K * ry), (cx + rx, cy + K * ry)),
                      ((cx, cy + ry), (cx + K * rx, cy + ry), (cx - K * rx, cy + ry)),
                      ((cx - rx, cy), (cx - rx, cy + K * ry), (cx - rx, cy - K * ry))):
        s.nodes.append({"p": p, "in": i_, "out": o_})
    s.closed = True
    return s


def _rect(x, y, w, h, rx, ry) -> _Sub:
    rx, ry = min(rx, w / 2), min(ry, h / 2)
    if rx <= 0 or ry <= 0:
        s = _Sub((x, y))
        for p in ((x + w, y), (x + w, y + h), (x, y + h)):
            s.line(p)
        s.closed = True
        return s
    kx, ky = K * rx, K * ry
    pts = [((x + rx, y), (x + rx - kx, y), None), ((x + w - rx, y), None, (x + w - rx + kx, y)),
           ((x + w, y + ry), (x + w, y + ry - ky), None), ((x + w, y + h - ry), None, (x + w, y + h - ry + ky)),
           ((x + w - rx, y + h), (x + w - rx + kx, y + h), None), ((x + rx, y + h), None, (x + rx - kx, y + h)),
           ((x, y + h - ry), (x, y + h - ry + ky), None), ((x, y + ry), None, (x, y + ry - ky))]
    s = _Sub(pts[0][0])
    s.nodes = [{"p": p, "in": i_, "out": o_} for p, i_, o_ in pts]
    s.closed = True
    return s


def _f(el, k, default=0.0) -> float:
    v = el.get(k)
    return float(v) if v not in (None, "") else default


def svg_to_shapes(svg_text: str, size: float = 24.0) -> list[dict]:
    root = ET.fromstring(svg_text)
    vb = [float(x) for x in (root.get("viewBox") or "0 0 24 24").replace(",", " ").split()]
    vx, vy, vw, vh = vb
    scale, cx0, cy0 = size / vw, vx + vw / 2, vy + vh / 2
    subs: list[_Sub] = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "path" and el.get("d"):
            subs += _path(el.get("d"))
        elif tag == "circle":
            subs.append(_ellipse(_f(el, "cx"), _f(el, "cy"), _f(el, "r"), _f(el, "r")))
        elif tag == "ellipse":
            subs.append(_ellipse(_f(el, "cx"), _f(el, "cy"), _f(el, "rx"), _f(el, "ry")))
        elif tag == "rect":
            rx = el.get("rx") or el.get("ry")
            ry = el.get("ry") or el.get("rx")
            subs.append(_rect(_f(el, "x"), _f(el, "y"), _f(el, "width"), _f(el, "height"),
                              float(rx) if rx else 0.0, float(ry) if ry else 0.0))
        elif tag == "line":
            s = _Sub((_f(el, "x1"), _f(el, "y1")))
            s.line((_f(el, "x2"), _f(el, "y2")))
            subs.append(s)
        elif tag in ("polyline", "polygon"):
            vals = [float(v) for v in _NUM.findall(el.get("points") or "")]
            pts = list(zip(vals[0::2], vals[1::2]))
            if len(pts) >= 2:
                s = _Sub(pts[0])
                for p in pts[1:]:
                    s.line(p)
                s.closed = tag == "polygon"
                subs.append(s)
    out = []
    for s in subs:
        if len(s.nodes) < 2:
            continue

        def T(q, base):
            return [0.0, 0.0] if q is None else [(q[0] - base[0]) * scale, (q[1] - base[1]) * scale]
        out.append({"vertices": [[(n["p"][0] - cx0) * scale, (n["p"][1] - cy0) * scale] for n in s.nodes],
                    "inTangents": [T(n["in"], n["p"]) for n in s.nodes],
                    "outTangents": [T(n["out"], n["p"]) for n in s.nodes], "closed": s.closed})
    return out


# --------------------------------------------------------------------------- index, search, mirror
@lru_cache(maxsize=1)
def load_index() -> dict:
    return (json.loads((ICON_DIR / "icons.json").read_text(encoding="utf-8")) or {}).get("icons", {})


def icon_svg(name: str) -> str:
    f = ICON_DIR / f"{name}.svg"
    if not f.exists():
        raise KeyError(name)
    return f.read_text(encoding="utf-8")


def icon_shapes(name: str, size: float, mirror: bool = False) -> list[dict]:
    shapes = svg_to_shapes(icon_svg(name), size)
    if mirror:
        for s in shapes:
            for key in ("vertices", "inTangents", "outTangents"):
                s[key] = [[-p[0], p[1]] for p in s[key]]
    return shapes


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def search(query: str, limit: int = 10) -> list[dict]:
    q = _tokens(query)
    hits = []
    for name, meta in load_index().items():
        nt, tags = set(_tokens(name)), {t.lower() for t in meta.get("tags", [])}
        score = sum(2 for t in q if t in nt) + sum(1 for t in q if t in tags)
        if name == "-".join(q):
            score += 5
        if score:
            hits.append({"name": name, "tags": meta.get("tags", []), "score": score})
    hits.sort(key=lambda h: (-h["score"], len(h["name"]), h["name"]))
    return hits[:limit]


def closest(name: str, n: int = 5) -> list[str]:
    names = list(load_index())
    flat = {x.replace("-", ""): x for x in names}
    got = difflib.get_close_matches(name.replace("-", ""), list(flat), n=n, cutoff=0.3)
    return [flat[g] for g in got]


def should_mirror(name: str, direction: str) -> bool:
    from .motion_config import motion_cfg
    return direction == "rtl" and name in set(motion_cfg().get("rtl_mirror_icons") or [])


# --------------------------------------------------------------------------- polylines (animatic, tests)
def _bez(p0, c1, c2, p3, t):
    u = 1 - t
    return (u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p3[1])


def flatten(shapes: list[dict], tol: float = 0.5) -> list[list[tuple[float, float]]]:
    polys = []
    for s in shapes:
        v, ti, to = s["vertices"], s["inTangents"], s["outTangents"]
        n = len(v)
        segs = list(range(n - 1)) + ([n - 1] if s["closed"] else [])
        pts = [tuple(v[0])]
        for k in segs:
            j = (k + 1) % n
            p0, p3 = v[k], v[j]
            c1 = (p0[0] + to[k][0], p0[1] + to[k][1])
            c2 = (p3[0] + ti[j][0], p3[1] + ti[j][1])
            if to[k] == [0.0, 0.0] and ti[j] == [0.0, 0.0]:
                pts.append(tuple(p3))
                continue
            length = math.dist(p0, c1) + math.dist(c1, c2) + math.dist(c2, p3)
            steps = max(4, int(math.ceil(length / max(tol, 1e-3))))
            pts += [_bez(p0, c1, c2, p3, i / steps) for i in range(1, steps + 1)]
        polys.append(pts)
    return polys
