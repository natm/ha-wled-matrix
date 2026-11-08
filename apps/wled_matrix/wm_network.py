"""Network screen: internet speed and line in use, drawn pixel by pixel.

Two styles (choose with `style`):

  big    Download in large digits (blue), upload below (orange), with the line in use and its latency along the
         top and a thin bar along the bottom showing how full the main line is. While the backup line is in use the
         name turns amber and "<MAIN> DOWN" flashes along the bottom. Almost no motion, so it looks the same by day
         and night.
  alert  An interrupt for a failover (use as a priority screen with `show_if` on the backup signal): red flashing
         border, "<MAIN> DOWN", "ON <BACKUP>" and the backup's speeds. If shown while the main line is up, it reads
         "<MAIN> BACK".

Speeds are always shown in the entity's unit, Mbit/s by default, with one small `unit_label` (no M/G switching:
a 1.8 Gbit/s line still fits in four digits). Latency is green under 25 ms, amber under 60, red above.

Pure Python, no dependencies; `t` is a time in seconds, used only for the flashing.
"""

from wm_glyphs import BIG
from wm_power import PowerCanvas
from wm_render import to_number
from wm_text import TEXT, TINY, text_width

DOWN = (0, 170, 255)     # download: blue, as on the classic internet screen
UP = (255, 150, 0)       # upload: orange
WHITE = (230, 230, 230)
LABEL = (120, 120, 120)  # the unit label, once
BAR_BG = (20, 20, 20)
BAD = (255, 40, 30)
GOOD = (0, 220, 90)
WARN = (240, 150, 0)     # amber: on the backup line

ARROW_D = ["00100", "00100", "11111", "01110", "00100"]
ARROW_U = ARROW_D[::-1]


def entities(cfg):
    """Every entity the screen reads."""
    out = []
    for link in cfg.get("links", []):
        for key in ("down", "up", "latency"):
            if link.get(key):
                out.append(link[key])
    if cfg.get("backup_active"):
        out.append(cfg["backup_active"])
    return out


def latency_colour(ms):
    if ms is None:
        return BAD
    return GOOD if ms < 25 else WARN if ms < 60 else BAD


def speed_text(v):
    if v is None:
        return "-"
    if v < 10:
        return f"{v:.1f}"
    return str(int(round(v)))


def readings(cfg, states):
    """The line in use and its numbers. The first link is the main line, the second the backup. The backup is in
    use while `backup_active` is on; without that signal, it's the main line unless the main line has no data."""
    links = cfg.get("links", [])
    if not links:
        return None
    main = links[0]
    backup = links[1] if len(links) > 1 else None

    def num(entity):
        return to_number(states.get(entity)) if entity else None

    on_backup = False
    flag = cfg.get("backup_active")
    if backup and flag:
        on_backup = str(states.get(flag)).lower() == "on"
    elif backup and num(main.get("down")) is None and num(backup.get("down")) is not None:
        on_backup = True
    link = backup if on_backup else main
    return {
        "on_backup": on_backup,
        "main": main.get("name", "MAIN"),
        "backup": (backup or {}).get("name", "BACKUP"),
        "name": link.get("name", ""),
        "icon": link.get("icon"),
        "down": num(link.get("down")),
        "up": num(link.get("up")),
        "latency": num(link.get("latency")),
        "max_down": float(main.get("max_down", 1000)),
    }


class NetCanvas(PowerCanvas):
    def glyph(self, rows, x, y, colour):
        for gy, row in enumerate(rows):
            for gx, bit in enumerate(row):
                if bit == "1":
                    self.put(x + gx, y + gy, colour)

    def big(self, s, x, y, colour, sc=2, align="left"):
        """Digits from the BIG font at `sc` times size."""
        w = big_width(s, sc)
        if align == "center":
            x -= w // 2
        elif align == "right":
            x -= w - 1
        for ch in s:
            g = BIG.get(ch)
            if not g:
                continue
            for gy, row in enumerate(g):
                for gx, bit in enumerate(row):
                    if bit == "1":
                        self.rect(x + gx * sc, y + gy * sc, x + gx * sc + sc - 1, y + gy * sc + sc - 1, colour)
            x += (len(g[0]) + 1) * sc
        return w

    def arrow_number(self, up, v, x, y, colour, align="left"):
        s = speed_text(v)
        w = 6 + text_width(s, TEXT)
        if align == "right":
            x -= w - 1
        elif align == "center":
            x -= w // 2
        self.glyph(ARROW_U if up else ARROW_D, x, y + 1, colour)
        self.text(s, x + 6, y, colour, TEXT)


def big_width(s, sc):
    widths = [(len(BIG[ch][0]) + 1) * sc for ch in s if ch in BIG]
    return sum(widths) - sc if widths else 0


def render_big(c, cfg, v, width, height, t, night, mdi):
    colour = WARN if v["on_backup"] else WHITE
    if v["icon"]:
        c.icon(mdi, v["icon"], 0, 0, 7, colour)
    c.text(v["name"], 9, 1, colour, TINY)
    if v["latency"] is not None:
        c.text(f"{int(round(v['latency']))}MS", width - 1, 1, latency_colour(v["latency"]), TINY, align="right")
    down = speed_text(v["down"])
    sc = 3 if big_width(down, 3) <= width - 2 else 2
    c.big(down, width // 2, 11 if sc == 3 else 15, DOWN, sc, align="center")
    c.text(cfg.get("unit_label", "MBIT/S"), width // 2, 35, LABEL, TINY, align="center")
    up = speed_text(v["up"])
    w = big_width(up, 2)
    x = width // 2 - (w + 7) // 2
    c.glyph(ARROW_U, x, 47, UP)
    c.big(up, x + 7, 43, UP, 2)
    if not v["on_backup"]:
        fill = min(1.0, max(0.0, (v["down"] or 0) / v["max_down"]))
        for xx in range(width):
            c.put(xx, height - 2, DOWN if xx < round(width * fill) else BAR_BG)
    elif night or int(t * 2) % 2 == 0:
        c.text(f"{v['main']} DOWN", width // 2, height - 5, BAD, TINY, align="center")


def render_alert(c, cfg, v, width, height, t, night, mdi):
    mid = width // 2
    if v["on_backup"]:
        if night or int(t * 2) % 2 == 0:
            for i in range(width):
                c.put(i, 0, BAD)
                c.put(i, height - 1, BAD)
            for i in range(height):
                c.put(0, i, BAD)
                c.put(width - 1, i, BAD)
        c.icon(mdi, cfg.get("alert_icon", "mdi:lan-disconnect"), mid - 12, 3, 24, BAD)
        title = f"{v['main']} DOWN"
        c.text(title, mid, 29, BAD, TEXT if text_width(title, TEXT) <= width - 4 else TINY, align="center")
        c.text(f"ON {v['backup']}", mid, 39, WARN, TINY, align="center")
        c.arrow_number(False, v["down"], 3, 47, DOWN)
        c.arrow_number(True, v["up"], width - 4, 47, UP, align="right")
        c.text(cfg.get("unit_label", "MBIT/S"), mid, 56, LABEL, TINY, align="center")
    else:
        c.icon(mdi, cfg.get("back_icon", "mdi:check-network"), mid - 12, 10, 24, GOOD)
        title = f"{v['main']} BACK"
        c.text(title, mid, 40, GOOD, TEXT if text_width(title, TEXT) <= width - 4 else TINY, align="center")


def render_network(cfg, states, width=64, height=64, mdi=None, t=0.0, night=False):
    """Pixels for a `network:` screen. `states` maps entity id to state string."""
    c = NetCanvas(width, height)
    v = readings(cfg, states)
    if v is None:
        c.text("NO LINKS", width // 2, height // 2 - 3, BAD, TINY, align="center")
        return c.px
    if cfg.get("style", "big") == "alert":
        render_alert(c, cfg, v, width, height, t, night, mdi)
    else:
        render_big(c, cfg, v, width, height, t, night, mdi)
    return c.px
