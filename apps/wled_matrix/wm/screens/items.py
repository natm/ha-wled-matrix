"""The rows / cells screen: items of icon + number + unit laid out in rows or a grid.

Pure Python, no dependencies. A frame is a list of (r, g, b) tuples, row by row.
"""

from ..utils.canvas import Canvas, draw_mdi
from ..utils.glyphs import BIG, ICONS, SMALL
from ..utils.text import text_width
from ..utils.values import format_value, pick_colour, pick_icon, to_number
from .base import Screen


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
        places = [
            (int(c.get("row", 0)), int(c.get("col", 0)), int(c.get("rowspan", 1)), int(c.get("colspan", 1)))
            for c in cells
        ]
    else:
        nrows, ncols = len(screen["rows"]), 1
        places = [(i, 0, 1, 1) for i in range(nrows)]

    def edge(n, count, total):  # integer cell boundaries that use the whole display
        return n * total // count

    return [
        (
            edge(c, ncols, width),
            edge(r, nrows, height),
            edge(c + cs, ncols, width) - edge(c, ncols, width),
            edge(r + rs, nrows, height) - edge(r, nrows, height),
        )
        for r, c, rs, cs in places
    ]


def ink_columns(rows, lit):
    """First and last column (from 0) with a lit pixel, or None for a blank icon."""
    cols = [x for row in rows for x, v in enumerate(row) if lit(v)]
    return (min(cols), max(cols)) if cols else None


def align_shift(left, right, x, w, align):
    """How far to move a group drawn from `left` to `right` so it sits left, center or right in the cell [x, x + w)."""
    if align == "center":
        return x + (w - (right - left + 1)) // 2 - left
    if align == "right":
        return x + w - 1 - right
    return 0


def draw_cell(c, item, value, rect, mdi, align="left"):
    """Icon on the left, then the number and unit, sized to fit the cell.

    `align` (the cell's own `align`, else the screen's) moves the icon and text together within the cell:
    `left` (default), `center` or `right`, measured on the pixels actually drawn.
    """
    x, y, w, h = rect
    align = item.get("align", align)
    colour = pick_colour(value, item)
    icon_colour = tuple(item["icon_colour"]) if "icon_colour" in item else colour
    icon = pick_icon(value, item) if item.get("icon") or item.get("icon_thresholds") else None
    text_x = x
    if "entity" not in item or item.get("show_value") is False:
        # Icon-only cell, centred: a label (no entity), or a status icon coloured by its entity's value.
        if icon and icon.startswith("mdi:") and mdi:
            size = int(item.get("icon_size", min(h, w, 24)))
            coverage = mdi.coverage(icon, size)
            if coverage:
                draw_mdi(c, coverage, x + (w - size) // 2, y + (h - size) // 2, icon_colour)
        elif icon and icon in ICONS:
            c.icon(icon, x + (w - 14) // 2, y + (h - 14) // 2, icon_colour)
        return
    # Work out the icon and text positions first, then shift the whole group for `align`.
    draw_icon = None
    left = x
    if icon and icon != "none":
        if icon.startswith("mdi:"):
            size = int(item.get("icon_size", min(h, 24, max(7, w // 3))))
            coverage = mdi.coverage(icon, size) if mdi else None
            if coverage:
                ink = ink_columns(coverage, lambda a: a > 0.15)
                left = x + ink[0] if ink else x
                draw_icon = lambda dx: draw_mdi(c, coverage, x + dx, y + (h - size) // 2, icon_colour)  # noqa: E731
            text_x = x + size + (3 if size >= 14 else 1)
        else:
            fill = None
            if item.get("fill") and value is not None:
                fill = (value / float(item.get("fill_max", 100)), colour)
            ink = ink_columns(ICONS[icon], lambda ch: ch in "OF") if icon in ICONS else None
            left = x + 1 + ink[0] if ink else x
            draw_icon = lambda dx: c.icon(icon, x + 1 + dx, y + (h - 14) // 2, icon_colour, fill)  # noqa: E731
            text_x = x + 18
    else:
        left = text_x
    number, unit = format_value(value, item.get("format", "number"))
    unit = item.get("unit", unit)
    room = x + w - text_x
    unit_w = text_width(unit, SMALL)
    # Big digits (2x, 14 px tall) when they fit, else the same font at 1x (7 px); drop the unit if still too wide.
    scales = (1,) if item.get("font") == "small" else (2, 1)  # `font: small` keeps rows consistent
    for scale in scales:
        num_w = text_width(number, BIG, scale)
        if h >= 7 * scale and num_w + (unit_w + 1 if unit else 0) <= room:
            break
    else:
        scale, unit = 1, ""
    num_w = text_width(number, BIG, scale)
    right = text_x + num_w + scale + unit_w - 1 if unit else text_x + num_w - 1
    dx = align_shift(left, right, x, w, align) if align in ("center", "right") else 0
    if draw_icon:
        draw_icon(dx)
    ty = y + (h - 7 * scale) // 2
    end = c.big(number, text_x + dx, ty, colour, scale)
    if unit:
        c.small(unit, end, ty + 7 * scale - 5, colour)


def render_screen(screen, values, width=64, height=64, mdi=None):
    """`screen` is a grid (`grid` + `cells`) or a list of `rows`; `values` are entity states (or numbers) in item order.

    `mdi` is an MdiIcons instance, used for icons named `mdi:<name>`.
    """
    c = Canvas(width, height)
    for item, state, rect in zip(items(screen), values, layout(screen, width, height)):
        draw_cell(c, item, to_number(state, item.get("format", "number")), rect, mdi, screen.get("align", "left"))
    return c.px


class ItemsScreen(Screen):
    """The default screen: `rows`, or `grid` + `cells`, of icon + number + unit. Selected when no other type's key is
    in the config, so it has no `key` of its own."""

    def entities(self):
        return [item["entity"] for item in items(self.screen) if "entity" in item]

    def render(self, width, height, *, night, t, now):
        values = [self.state(item["entity"]) if "entity" in item else None for item in items(self.screen)]
        return render_screen(self.screen, values, width, height, self.mdi)
