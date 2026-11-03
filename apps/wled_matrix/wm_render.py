"""Draw a screen of rows (icon + big number + small unit) into a width x height RGB frame.

Pure Python, no dependencies. A frame is a list of (r, g, b) tuples, row by row.
"""

from wm_glyphs import BIG, SMALL, ICONS

BLACK = (0, 0, 0)


class Canvas:
    def __init__(self, width, height):
        self.w, self.h = width, height
        self.px = [BLACK] * (width * height)

    def put(self, x, y, colour):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y * self.w + x] = colour

    def icon(self, name, x0, y0, colour, fill=None):
        """Draw a 14x14 icon. `fill` = (fraction 0..1, colour) fills the icon's 'F' area left to right."""
        rows = ICONS[name]
        fill_cells = [(x, y) for y, r in enumerate(rows) for x, ch in enumerate(r) if ch == "F"]
        if fill and fill_cells:
            frac, fcol = fill
            xs = sorted({x for x, _ in fill_cells})
            limit = xs[0] + round(len(xs) * max(0.0, min(1.0, frac)))
            for x, y in fill_cells:
                if x < limit:
                    self.put(x0 + x, y0 + y, fcol)
        for y, r in enumerate(rows):
            for x, ch in enumerate(r):
                if ch == "O":
                    self.put(x0 + x, y0 + y, colour)

    def big(self, text, x0, y0, colour, scale=2):
        x = x0
        for ch in text:
            glyph = BIG.get(ch)
            if glyph is None:
                continue
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit == "1":
                        for dy in range(scale):
                            for dx in range(scale):
                                self.put(x + gx * scale + dx, y0 + gy * scale + dy, colour)
            x += (len(glyph[0]) + 1) * scale
        return x

    def small(self, text, x0, y0, colour):
        x = x0
        for ch in text:
            glyph = SMALL.get(ch)
            if glyph is None:
                continue
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit == "1":
                        self.put(x + gx, y0 + gy, colour)
            x += len(glyph[0]) + 1
        return x


def format_value(value, fmt):
    """Return (number text, unit text) for a row."""
    if value is None:
        return "-", ""
    if fmt == "percent":
        return str(int(round(max(0, min(100, value))))), "%"
    if fmt == "power":  # watts in, W or kW out
        w = int(round(value))
        if abs(w) >= 1000:
            return f"{w / 1000:.1f}", "kW"
        return str(w), "W"
    if fmt == "number":
        return str(int(round(value))), ""
    if fmt.startswith("decimal"):  # e.g. decimal1
        return f"{value:.{int(fmt[7:] or 1)}f}", ""
    return str(value), ""


def pick_colour(value, row):
    """A row's colour: fixed `colour`, or the first `thresholds` entry whose `above` the value exceeds."""
    for t in row.get("thresholds", []):
        if value is not None and value >= t["above"]:
            return tuple(t["colour"])
    return tuple(row.get("colour", (200, 200, 200)))


def render_screen(screen, values, width=64, height=64):
    """`screen` = {"rows": [...]}, `values` = list of floats (or None) in row order."""
    c = Canvas(width, height)
    rows = screen["rows"]
    pitch = height // max(1, len(rows))
    for i, (row, value) in enumerate(zip(rows, values)):
        y0 = i * pitch + max(0, (pitch - 14) // 2)
        colour = pick_colour(value, row)
        fill = None
        if row.get("fill") and value is not None:
            fill = (value / float(row.get("fill_max", 100)), colour)
        icon_colour = tuple(row["icon_colour"]) if "icon_colour" in row else colour
        c.icon(row["icon"], 1, y0, icon_colour, fill)
        number, unit = format_value(value, row.get("format", "number"))
        unit = row.get("unit", unit)
        end = c.big(number, 18, y0, colour)
        c.small(unit, end, y0 + 9, colour)
    return c.px
