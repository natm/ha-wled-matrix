"""The pixel canvas every screen draws on, and the drawing helpers shared between screens.

A frame is a list of (r, g, b) tuples, row by row. `Canvas` has the number fonts and the built-in 14x14 icons;
`TextCanvas` adds letters (`text`, `number`), MDI icons by name, rectangles and raw bitmaps, for screens that lay
out their own text rather than icon + number rows.
"""

from .glyphs import BIG, ICONS, SMALL
from .text import TEXT, TINY, draw_text, text_width

BLACK = (0, 0, 0)
GREY = (120, 120, 120)


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


def draw_mdi(canvas, coverage, x0, y0, colour):
    """Draw a coverage map, scaling the colour by each pixel's coverage so curved edges look smooth."""
    for y, row in enumerate(coverage):
        for x, a in enumerate(row):
            if a > 0.15:
                canvas.put(x0 + x, y0 + y, tuple(int(ch * min(1.0, a * 1.2)) for ch in colour))


def scale(colour, k):
    """`colour` at brightness `k` (0..1)."""
    return tuple(max(0, min(255, int(v * k))) for v in colour)


class TextCanvas(Canvas):
    """A canvas with letter text, MDI icons by name, rectangles and bitmaps (alignment: left, center or right)."""

    def rect(self, x0, y0, x1, y1, colour):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.put(x, y, colour)

    def icon(self, mdi, name, x, y, size, colour):
        coverage = mdi.coverage(name, size) if mdi else None
        if coverage:
            draw_mdi(self, coverage, x, y, colour)

    def glyph(self, rows, x, y, colour):
        """A bitmap given as rows of '0'/'1' strings."""
        for gy, row in enumerate(rows):
            for gx, bit in enumerate(row):
                if bit == "1":
                    self.put(x + gx, y + gy, colour)

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
