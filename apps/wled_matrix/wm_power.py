"""Power-flow screen: where the power is going now, as an animated diagram.

Sun and solar power top left, the grid pylon top right, the battery gauge and charge bottom left, the car and its
charging power bottom right, and the house and its load in the middle. A line joins each to the house; bright dots
move along it in the direction of flow, faster with more power. Anything below `idle_w` is grey and still.

Pure Python, no dependencies. `t` is a time in seconds: the dots are placed from it, so frames drawn at any rate
line up (the app redraws this screen `frame_rate` times a second while it's showing). At night the dots stand still.
"""

import math

from wm_render import Canvas, draw_mdi, to_number
from wm_text import TEXT, TINY, draw_text, text_width

ROLES = ("solar", "grid", "battery", "soc", "load", "ev")

DEFAULT_COLOURS = {
    "solar": [255, 200, 0],     # sun and solar energy
    "import": [255, 60, 30],    # grid import
    "export": [0, 220, 90],     # grid export
    "battery": [40, 120, 255],  # battery charging or discharging
    "ev": [0, 200, 255],        # car charging
    "house": [230, 230, 230],
    "idle": [70, 70, 70],       # anything at 0 W
    "line": [28, 28, 28],       # an idle line
    "moon": [90, 90, 140],
    "outline": [150, 150, 150],  # battery outline
}
DEFAULT_SOC = [  # first entry whose `above` the charge reaches; under all of them: `soc_colour`
    {"above": 30, "colour": [0, 200, 0]},
    {"above": 20, "colour": [240, 150, 0]},
]
DEFAULT_SOC_LOW = [230, 0, 0]

# Lines from each corner to the house, as polylines (64 x 64 layout). They start below the corner numbers and end at
# the house icon's sides, so no line touches a number.
PATHS = {
    "solar": [(8, 22), (14, 28), (23, 28)],
    "grid": [(55, 22), (49, 28), (40, 28)],
    "battery": [(12, 39), (16, 35), (23, 35)],
    "ev": [(40, 35), (45, 35), (50, 40)],
}


def scale(colour, k):
    return tuple(max(0, min(255, int(v * k))) for v in colour)


def kw(watts, idle_w=50):
    """Power as kW with one decimal (no unit, to save room), "0" when idle, "-" when unknown."""
    if watts is None:
        return "-"
    w = abs(watts)
    if w < idle_w:
        return "0"
    return f"{w / 1000:.1f}" if w < 99950 else str(int(round(w / 1000)))


def bresenham(x0, y0, x1, y1):
    pts, dx, dy = [], abs(x1 - x0), -abs(y1 - y0)
    sx, sy, err = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1), abs(x1 - x0) - abs(y1 - y0)
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            return pts
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def path_points(pts):
    """Every pixel along a polyline, in order, without repeating the joints."""
    out = []
    for (a, b), (c, d) in zip(pts, pts[1:]):
        seg = bresenham(a, b, c, d)
        out.extend(seg if not out else seg[1:])
    return out


def dot_speed(watts, max_w, slow=4.0, fast=16.0):
    """Pixels per second a dot moves: `slow` at a trickle, `fast` from `max_w` up."""
    frac = max(0.0, min(1.0, abs(watts) / max_w)) if max_w > 0 else 1.0
    return slow + (fast - slow) * frac


class PowerCanvas(Canvas):
    def rect(self, x0, y0, x1, y1, colour):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.put(x, y, colour)

    def icon(self, mdi, name, x, y, size, colour):
        coverage = mdi.coverage(name, size) if mdi else None
        if coverage:
            draw_mdi(self, coverage, x, y, colour)

    def text(self, s, x, y, colour, font=TEXT, align="left"):
        w = text_width(s, font)
        if align == "right":
            x -= w - 1
        elif align == "center":
            x -= w // 2
        return draw_text(self, s, x, y, colour, font)

    def number(self, num, unit, x, y, colour, align="left"):
        """A 5x7 number, then an optional 3x5 unit sitting on its baseline."""
        w = text_width(num, TEXT) + (1 + text_width(unit, TINY) if unit else 0)
        if align == "right":
            x -= w - 1
        elif align == "center":
            x -= w // 2
        end = draw_text(self, num, x, y, colour, TEXT)
        if unit:
            draw_text(self, unit, end, y + 2, scale(colour, 0.7), TINY)

    def flow(self, pts, colour, watts, t, idle_w, max_w, reverse=False, spacing=6, line=(28, 28, 28)):
        """A dim line with bright dots (each with a short tail) moving along it, faster with more power."""
        points = path_points(pts)
        if reverse:
            points = points[::-1]
        if watts is None or abs(watts) < idle_w:
            for x, y in points:
                self.put(x, y, line)
            return
        for x, y in points:
            self.put(x, y, scale(colour, 0.3))
        offset = int(t * dot_speed(watts, max_w)) % spacing
        for i, (x, y) in enumerate(points):
            if (i - offset) % spacing == 0:
                self.put(x, y, colour)
                if i > 0:
                    self.put(*points[i - 1], scale(colour, 0.45))  # tail behind the dot shows the direction

    def battery(self, x0, y0, w, h, soc, colour, outline, watts, t, idle_w):
        """Upright battery: cap, outline, filled from the bottom by charge; the edge of the fill pulses while it
        charges or discharges."""
        cap = max(2, w // 3)
        cx = x0 + (w - cap) // 2
        self.rect(cx, y0, cx + cap - 1, y0 + 1, outline)
        top = y0 + 2
        for x in range(x0, x0 + w):
            self.put(x, top, outline)
            self.put(x, y0 + h - 1, outline)
        for y in range(top, y0 + h):
            self.put(x0, y, outline)
            self.put(x0 + w - 1, y, outline)
        inner = h - 4
        rows = round(inner * max(0.0, min(100.0, soc or 0)) / 100)
        for r in range(inner):
            y = y0 + h - 2 - r
            for x in range(x0 + 1, x0 + w - 1):
                self.put(x, y, colour if r < rows else (12, 12, 12))
        if watts is None or abs(watts) < idle_w:
            return
        pulse = 0.5 + 0.5 * math.sin(t * 2 * math.pi / 2.0)  # one pulse every 2 s
        if watts > 0 and rows < inner:  # charging: the row above the fill glows
            r, k = rows, 0.25 + 0.5 * pulse
        elif watts < 0 and rows > 0:  # discharging: the top row of the fill fades
            r, k = rows - 1, 0.4 + 0.6 * pulse
        else:
            return
        for x in range(x0 + 1, x0 + w - 1):
            self.put(x, y0 + h - 2 - r, scale(colour, k))


def soc_colour(soc, cfg):
    for t in cfg.get("soc_thresholds", DEFAULT_SOC):
        if soc is not None and soc >= t["above"]:
            return tuple(t["colour"])
    return tuple(cfg.get("soc_colour", DEFAULT_SOC_LOW))


def entities(cfg):
    """Every entity the screen reads, as (role, entity) pairs; `solar` may list several, which are added up."""
    out = []
    for role in ROLES:
        ids = cfg.get(role)
        if ids is None:
            continue
        for entity in ([ids] if isinstance(ids, str) else ids):
            out.append((role, entity))
    return out


def readings(cfg, states):
    """Numbers per role from {entity: state}. Several solar entities are summed (unknown ones skipped); a role with
    no known value is None. With `load_includes_ev`, the house figure is the load minus the car."""
    vals = {}
    for role, entity in entities(cfg):
        n = to_number(states.get(entity))
        if n is None:
            vals.setdefault(role, None)
        else:
            vals[role] = (vals.get(role) or 0.0) + n
    for role in ROLES:
        vals.setdefault(role, None)
    house = vals["load"]
    if house is not None and cfg.get("load_includes_ev") and vals["ev"] is not None:
        house = max(0.0, house - vals["ev"])
    vals["house"] = house
    return vals


def render_power_flow(cfg, states, width=64, height=64, mdi=None, t=0.0, night=False):
    """`cfg` is the screen's `power_flow:` block, `states` maps entity ids to their states."""
    col = {k: tuple(v) for k, v in {**DEFAULT_COLOURS, **cfg.get("colours", {})}.items()}
    idle_w = float(cfg.get("idle_w", 50))
    max_w = float(cfg.get("max_kw", 10)) * 1000
    v = readings(cfg, states)
    if night:
        t = 0.0  # dots stand still at night
    c = PowerCanvas(width, height)
    live = lambda w: w is not None and abs(w) >= idle_w  # noqa: E731

    solar, grid, batt, ev = v["solar"], v["grid"], v["battery"], v["ev"]
    gcol = col["import"] if live(grid) and grid > 0 else col["export"] if live(grid) else col["idle"]
    # The car's line takes the colour of the biggest supply right now.
    sources = [(solar or 0, col["solar"]), (max(grid or 0, 0), col["import"]), (max(-(batt or 0), 0), col["battery"])]
    biggest = max(sources, key=lambda s: s[0])
    supply = biggest[1] if biggest[0] >= idle_w else col["idle"]

    kw_args = dict(idle_w=idle_w, max_w=max_w, line=col["line"])
    c.flow(PATHS["solar"], col["solar"], solar, t, **kw_args)
    c.flow(PATHS["grid"], gcol, grid, t, reverse=live(grid) and grid < 0, **kw_args)
    c.flow(PATHS["battery"], col["battery"], batt, t, reverse=live(batt) and batt > 0, **kw_args)
    c.flow(PATHS["ev"], supply, ev, t, **kw_args)

    # Solar, top left
    if live(solar):
        c.icon(mdi, "mdi:white-balance-sunny", 0, 0, 13, col["solar"])
        c.number(kw(solar, idle_w), "", 0, 14, col["solar"])
    else:
        c.icon(mdi, "mdi:weather-night" if night or solar is not None else "mdi:white-balance-sunny", 0, 0, 13,
               col["moon"])
        c.text(kw(solar, idle_w), 1, 14, col["idle"])
    # Grid, top right
    c.icon(mdi, "mdi:transmission-tower", 51, 0, 13, gcol)
    c.number(kw(grid, idle_w), "", 62, 14, gcol, align="right")
    # House, middle
    c.icon(mdi, "mdi:home", 24, 21, 16, col["house"])
    c.number(kw(v["house"], idle_w), "", 32, 38, col["house"], align="center")
    # Battery, bottom left
    soc = v["soc"]
    scol = soc_colour(soc, cfg)
    c.battery(1, 41, 11, 15, soc, scol, col["outline"], batt, t, idle_w)
    c.number("-" if soc is None else str(int(round(max(0, min(100, soc))))), "%", 0, 56, scol)
    # Car, bottom right
    ecol = col["ev"] if live(ev) else col["idle"]
    c.icon(mdi, "mdi:car-electric", 51, 42, 13, ecol)
    c.number(kw(ev, idle_w), "", 62, 56, ecol, align="right")
    return c.px
