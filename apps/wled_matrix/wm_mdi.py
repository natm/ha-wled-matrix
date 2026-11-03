"""Material Design Icons for the matrix, converted at run time.

The icon outlines are not stored in this project. On first use the official `@mdi/js` package (one JavaScript file
holding every icon's SVG path) is downloaded once from jsDelivr and cached on disk; each icon is then rasterised
here in pure Python: the SVG path is flattened to polygons, filled with the non-zero rule at 4x4 samples per pixel,
and kept as a per-pixel coverage map (0..1), so edges can be drawn at partial brightness.
"""

import json
import math
import os
import re
import urllib.request

MDI_VERSION = "7.4.47"
MDI_URL = "https://cdn.jsdelivr.net/npm/@mdi/js@{version}/mdi.js"
VIEWBOX = 24.0  # every MDI icon is drawn on a 24x24 grid
SAMPLES = 4  # samples per pixel, per axis

_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


def _js_name(icon):
    """'mdi:transmission-tower' -> 'mdiTransmissionTower'."""
    name = icon.split(":", 1)[1] if ":" in icon else icon
    return "mdi" + "".join(part[:1].upper() + part[1:] for part in name.split("-"))


class MdiIcons:
    def __init__(self, cache_dir, version=MDI_VERSION, log=print):
        self.cache_dir = cache_dir
        self.version = version
        self.log = log
        self.paths = None
        self.bitmaps = {}

    def _load(self):
        if self.paths is not None:
            return
        os.makedirs(self.cache_dir, exist_ok=True)
        cache = os.path.join(self.cache_dir, f"mdi-{self.version}.json")
        if os.path.exists(cache):
            with open(cache) as f:
                self.paths = json.load(f)
            return
        url = MDI_URL.format(version=self.version)
        self.log(f"Downloading Material Design Icons {self.version} from {url}")
        with urllib.request.urlopen(url, timeout=60) as r:
            text = r.read().decode()
        self.paths = dict(re.findall(r'export var (mdi\w+) = "([^"]+)";', text))
        with open(cache, "w") as f:
            json.dump(self.paths, f)
        self.log(f"Cached {len(self.paths)} icons in {cache}")

    def coverage(self, icon, size):
        """Return a size x size list of rows of coverage values (0..1), or None if the icon doesn't exist."""
        key = (icon, size)
        if key in self.bitmaps:
            return self.bitmaps[key]
        self._load()
        path = self.paths.get(_js_name(icon))
        bitmap = rasterise(path, size) if path else None
        self.bitmaps[key] = bitmap
        return bitmap


def rasterise(path, size):
    edges = []
    for poly in _polygons(path):
        for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
            if y1 != y2:
                edges.append((x1, y1, x2, y2))
    scale = size / VIEWBOX
    n = size * SAMPLES
    rows = []
    for py in range(size):
        row = []
        for px in range(size):
            hits = 0
            for sy in range(SAMPLES):
                y = (py * SAMPLES + sy + 0.5) / SAMPLES / scale
                for sx in range(SAMPLES):
                    x = (px * SAMPLES + sx + 0.5) / SAMPLES / scale
                    winding = 0
                    for x1, y1, x2, y2 in edges:
                        if (y1 <= y) != (y2 <= y):
                            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                            if xi > x:
                                winding += 1 if y2 > y1 else -1
                    if winding:
                        hits += 1
            row.append(hits / (SAMPLES * SAMPLES))
        rows.append(row)
    return rows


def _polygons(d):
    """Flatten an SVG path into closed polygons (lists of points)."""
    tokens = _TOKEN.findall(d)
    polys, poly = [], []
    x = y = sx = sy = 0.0
    last_ctrl = None
    cmd = None
    i = 0

    def num():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
            if cmd in "Zz":
                if poly:
                    polys.append(poly)
                poly = []
                x, y = sx, sy
                last_ctrl = None
                continue
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            if poly:
                polys.append(poly)
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            sx, sy = x, y
            poly = [(x, y)]
            cmd = "l" if rel else "L"  # further pairs are line-tos
            last_ctrl = None
        elif c == "L":
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            poly.append((x, y))
            last_ctrl = None
        elif c == "H":
            nx = num()
            x = x + nx if rel else nx
            poly.append((x, y))
            last_ctrl = None
        elif c == "V":
            ny = num()
            y = y + ny if rel else ny
            poly.append((x, y))
            last_ctrl = None
        elif c in "CS":
            if c == "C":
                x1, y1 = num(), num()
                if rel:
                    x1, y1 = x + x1, y + y1
            else:
                x1, y1 = (2 * x - last_ctrl[0], 2 * y - last_ctrl[1]) if last_ctrl and last_ctrl[2] == "C" else (x, y)
            x2, y2, ex, ey = num(), num(), num(), num()
            if rel:
                x2, y2, ex, ey = x + x2, y + y2, x + ex, y + ey
            for t in (k / 8 for k in range(1, 9)):
                u = 1 - t
                poly.append((u ** 3 * x + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 * ex,
                             u ** 3 * y + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * ey))
            last_ctrl = (x2, y2, "C")
            x, y = ex, ey
        elif c in "QT":
            if c == "Q":
                x1, y1 = num(), num()
                if rel:
                    x1, y1 = x + x1, y + y1
            else:
                x1, y1 = (2 * x - last_ctrl[0], 2 * y - last_ctrl[1]) if last_ctrl and last_ctrl[2] == "Q" else (x, y)
            ex, ey = num(), num()
            if rel:
                ex, ey = x + ex, y + ey
            for t in (k / 8 for k in range(1, 9)):
                u = 1 - t
                poly.append((u * u * x + 2 * u * t * x1 + t * t * ex, u * u * y + 2 * u * t * y1 + t * t * ey))
            last_ctrl = (x1, y1, "Q")
            x, y = ex, ey
        elif c == "A":
            rx, ry, rot, large, sweep = num(), num(), num(), num(), num()
            ex, ey = num(), num()
            if rel:
                ex, ey = x + ex, y + ey
            poly.extend(_arc(x, y, rx, ry, rot, large, sweep, ex, ey))
            x, y = ex, ey
            last_ctrl = None
        else:
            i += 1  # unknown token; skip
    if poly:
        polys.append(poly)
    return [p for p in polys if len(p) > 2]


def _arc(x1, y1, rx, ry, rot, large, sweep, x2, y2):
    """Points along an SVG elliptical arc (endpoint form), excluding the start point."""
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [(x2, y2)]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(rot)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cos_p * dx + sin_p * dy, -sin_p * dx + cos_p * dy
    lam = (x1p ** 2) / (rx ** 2) + (y1p ** 2) / (ry ** 2)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num_ = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = math.sqrt(max(0.0, num_ / den)) if den else 0.0
    if bool(large) == bool(sweep):
        coef = -coef
    cxp, cyp = coef * rx * y1p / ry, -coef * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (x1 + x2) / 2
    cy = sin_p * cxp + cos_p * cyp + (y1 + y2) / 2

    def angle(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    steps = max(4, int(abs(dt) / (math.pi / 12)))
    pts = []
    for k in range(1, steps + 1):
        t = t1 + dt * k / steps
        px, py = rx * math.cos(t), ry * math.sin(t)
        pts.append((cos_p * px - sin_p * py + cx, sin_p * px + cos_p * py + cy))
    return pts
