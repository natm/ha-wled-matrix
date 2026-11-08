"""Stars screen: weekly star points for children (e.g. up to 7 stars a week, with a yearly total).

Two styles (choose with `style`):

  week   Each child's name in their colour, a row of stars (gold when earned, dim when not), "5/7" and
         "YEAR 41". Fits two children on a 64x64 matrix.
  alert  A pop-up after a star is added or taken away (use as a priority screen with `show_if`). Reads who and
         what from the `alert` entity, e.g. "dylan,+" or "seth,-": a shooting star with twinkles and WELL DONE
         for a +, a trophy and "7 STARS!" for a full week, a calm grey STAR OFF for a -.

Pure Python, no dependencies; `t` is a time in seconds (the twinkles), still at night.
"""

from wm_power import PowerCanvas
from wm_render import to_number
from wm_text import TEXT, TINY, text_width

GOLD = (255, 200, 0)
DIM = (55, 45, 20)
WHITE = (230, 230, 230)
GREY = (120, 120, 120)
DEFAULT_COLOUR = (230, 230, 230)


def entities(cfg):
    out = []
    for kid in cfg.get("kids", []):
        out += [kid[k] for k in ("week", "year") if kid.get(k)]
    if cfg.get("alert"):
        out.append(cfg["alert"])
    return out


def kid_values(kid, states):
    week = to_number(states.get(kid.get("week")))
    year = to_number(states.get(kid.get("year")))
    return (int(week) if week is not None else 0), (int(year) if year is not None else None)


def stars_row(c, mdi, y, n, most=7, size=7, gap=2, width=64):
    x = (width - (most * size + (most - 1) * gap)) // 2
    for i in range(most):
        c.icon(mdi, "mdi:star", x + i * (size + gap), y, size, GOLD if i < n else DIM)


def render_week(c, cfg, states, width, height, mdi):
    most = int(cfg.get("most", 7))
    c.text(cfg.get("title", "STARS"), width // 2, 0, GOLD, TINY, align="center")
    for i, kid in enumerate(cfg.get("kids", [])[:2]):
        top = 8 + i * 28
        colour = tuple(kid.get("colour", DEFAULT_COLOUR))
        week, year = kid_values(kid, states)
        c.text(str(kid.get("name", "")).upper(), 1, top, colour, TINY)
        c.text(f"{week}/{most}", width - 1, top, WHITE, TINY, align="right")
        stars_row(c, mdi, top + 8, week, most, width=width)
        if year is not None:
            c.text(f"YEAR {year}", width // 2, top + 18, GREY, TINY, align="center")


def parse_alert(value):
    """'dylan,+' -> ('dylan', True); '' or junk -> (None, True)."""
    parts = str(value or "").split(",")
    who = parts[0].strip().lower() or None
    plus = not (len(parts) > 1 and parts[1].strip() == "-")
    return who, plus


def render_alert(c, cfg, states, width, height, t, night, mdi):
    most = int(cfg.get("most", 7))
    who, plus = parse_alert(states.get(cfg.get("alert")))
    kid = next((k for k in cfg.get("kids", []) if str(k.get("id", k.get("name", ""))).lower() == who), None)
    if kid is None:
        return
    colour = tuple(kid.get("colour", DEFAULT_COLOUR))
    week, year = kid_values(kid, states)
    mid = width // 2
    if plus:
        c.icon(mdi, "mdi:trophy" if week >= most else "mdi:star-shooting", mid - 12, 1, 24, GOLD)
        phase = 0 if night else int(t * 3)
        for i, (x, y) in enumerate(((6, 6), (54, 4), (10, 22), (56, 20), (3, 14), (60, 12))):
            if (i + phase) % 2 == 0:
                c.put(x, y, WHITE)
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    c.put(x + dx, y + dy, GOLD)
        msg = f"{most} STARS!" if week >= most else "WELL DONE"
        c.text(msg, mid, 27, GOLD, TEXT if text_width(msg, TEXT) <= width - 2 else TINY, align="center")
    else:
        c.icon(mdi, "mdi:star-minus-outline", mid - 10, 2, 20, GREY)
        c.text("STAR OFF", mid, 27, GREY, TEXT, align="center")
    name = str(kid.get("name", "")).upper()
    c.text(name, mid, 37, colour, TEXT if text_width(name, TEXT) <= width - 2 else TINY, align="center")
    stars_row(c, mdi, 47, week, most, width=width)
    c.text(f"{week}/{most}  YEAR {year}" if year is not None else f"{week}/{most}", mid, 58, GREY, TINY,
           align="center")


def render_stars(cfg, states, width=64, height=64, mdi=None, t=0.0, night=False):
    """Pixels for a `stars:` screen. `states` maps entity id to state string."""
    c = PowerCanvas(width, height)
    if cfg.get("style", "week") == "alert":
        render_alert(c, cfg, states, width, height, t, night, mdi)
    else:
        render_week(c, cfg, states, width, height, mdi)
    return c.px
