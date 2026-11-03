"""Draw a screen of items (icon + number + unit) laid out in rows or a grid, into a width x height RGB frame.

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


def pick_icon(value, row):
    """A row's icon: the first `icon_thresholds` entry whose `above` the value reaches, else `icon`."""
    for t in row.get("icon_thresholds", []):
        if value is not None and value >= t["above"]:
            return t["icon"]
    return row["icon"]


def draw_mdi(canvas, coverage, x0, y0, colour):
    """Draw a coverage map, scaling the colour by each pixel's coverage so curved edges look smooth."""
    for y, row in enumerate(coverage):
        for x, a in enumerate(row):
            if a > 0.15:
                canvas.put(x0 + x, y0 + y, tuple(int(ch * min(1.0, a * 1.2)) for ch in colour))


def text_width(text, font, scale=1):
    widths = [(len(font[ch][0]) + 1) * scale for ch in text if ch in font]
    return sum(widths) - scale if widths else 0


def items(screen):
    """A screen's items in value order: grid `cells`, or legacy `rows` (one full-width cell per row)."""
    return screen["cells"] if "cells" in screen else screen["rows"]


def layout(screen, width, height):
    """Pixel rectangle (x, y, w, h) for each item.

    Grid screens: `grid: {rows, columns}`, and each cell gives `row`, `col`, optional `rowspan`, `colspan`.
    Legacy screens with `rows` are a one-column grid.
    """
    if "cells" in screen:
        grid = screen.get("grid", {})
        nrows, ncols = int(grid.get("rows", 1)), int(grid.get("columns", 1))
        cells = screen["cells"]
        places = [(int(c.get("row", 0)), int(c.get("col", 0)), int(c.get("rowspan", 1)), int(c.get("colspan", 1)))
                  for c in cells]
    else:
        nrows, ncols = len(screen["rows"]), 1
        places = [(i, 0, 1, 1) for i in range(nrows)]

    def edge(n, count, total):  # integer cell boundaries that use the whole display
        return n * total // count

    return [(edge(c, ncols, width), edge(r, nrows, height),
             edge(c + cs, ncols, width) - edge(c, ncols, width),
             edge(r + rs, nrows, height) - edge(r, nrows, height)) for r, c, rs, cs in places]


def draw_cell(c, item, value, rect, mdi):
    """Icon on the left, then the number and unit, sized to fit the cell."""
    x, y, w, h = rect
    colour = pick_colour(value, item)
    icon_colour = tuple(item["icon_colour"]) if "icon_colour" in item else colour
    icon = pick_icon(value, item) if item.get("icon") or item.get("icon_thresholds") else None
    text_x = x
    if icon and icon != "none":
        if icon.startswith("mdi:"):
            size = int(item.get("icon_size", min(h, 24, max(7, w // 3))))
            coverage = mdi.coverage(icon, size) if mdi else None
            if coverage:
                draw_mdi(c, coverage, x, y + (h - size) // 2, icon_colour)
            text_x = x + size + (3 if size >= 14 else 1)
        else:
            fill = None
            if item.get("fill") and value is not None:
                fill = (value / float(item.get("fill_max", 100)), colour)
            c.icon(icon, x + 1, y + (h - 14) // 2, icon_colour, fill)
            text_x = x + 18
    number, unit = format_value(value, item.get("format", "number"))
    unit = item.get("unit", unit)
    room = x + w - text_x
    unit_w = text_width(unit, SMALL)
    # Big digits (2x, 14 px tall) when they fit, else the same font at 1x (7 px); drop the unit if still too wide.
    for scale in (2, 1):
        num_w = text_width(number, BIG, scale)
        if h >= 7 * scale and num_w + (unit_w + 1 if unit else 0) <= room:
            break
    else:
        scale, unit = 1, ""
    ty = y + (h - 7 * scale) // 2
    end = c.big(number, text_x, ty, colour, scale)
    if unit:
        c.small(unit, end, ty + 7 * scale - 5, colour)


def render_screen(screen, values, width=64, height=64, mdi=None):
    """`screen` is a grid (`grid` + `cells`) or a list of `rows`; `values` are floats (or None) in item order.

    `mdi` is an MdiIcons instance, used for icons named `mdi:<name>`.
    """
    c = Canvas(width, height)
    for item, value, rect in zip(items(screen), values, layout(screen, width, height)):
        draw_cell(c, item, value, rect, mdi)
    return c.px
