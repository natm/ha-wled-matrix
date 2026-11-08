"""Aircraft screens: live aircraft near home on the matrix, from your own ADS-B receiver.

Styles: `radar` (north up, home in the middle, an arrow per aircraft coloured by height), `nearest` (the closest aircraft:
callsign, type, distance, direction, height and speed, with the others paging along the bottom), `board` (the four
nearest, two lines each) and `alert` (a flashing card for an "interesting" aircraft: low flyer, helicopter, military,
emergency squawk or overhead).

Data comes from either:
- `url`: a readsb / tar1090 / dump1090-fa `aircraft.json` (read at most once a second, shared by all matrices); or
- `entity`: a Home Assistant entity whose `aircraft` attribute is a list of readsb-style items (`hex`, `flight`, `lat`,
  `lon`, `alt_baro`, `track`, `gs`, `category`, `squawk`; optional `interesting`, `route`, `type`).
Distances and bearings are worked out here from the home point; items without a position but with `km` and
`bearing` are used as they are.
"""

import json
import math
import time
import urllib.request

from wm_render import Canvas, draw_mdi
from wm_text import TEXT, TINY, draw_text, text_width

EARTH_KM = 6371.0088
COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
ARROWS = ["mdi:arrow-up", "mdi:arrow-top-right", "mdi:arrow-right", "mdi:arrow-bottom-right",
          "mdi:arrow-down", "mdi:arrow-bottom-left", "mdi:arrow-left", "mdi:arrow-top-left"]
KINDS = {"A1": "LIGHT", "A2": "SMALL", "A3": "AIRLINER", "A4": "AIRLINER", "A5": "HEAVY", "A6": "FAST JET",
         "A7": "HELICOPTER", "B1": "GLIDER", "B2": "BALLOON", "B4": "MICROLIGHT", "B6": "DRONE"}
SQUAWKS = {"7500": "HIJACK", "7600": "NO RADIO", "7700": "EMERGENCY"}

DEFAULT_COLOURS = {
    "ring": [0, 45, 18], "house": [210, 210, 210], "text": [110, 110, 110], "label": [210, 210, 210],
    "accent": [255, 170, 0], "ticker": [0, 150, 255], "ground": [90, 90, 90], "marker": [150, 150, 150],
    "coast": [0, 55, 110],
}
DEFAULT_BANDS = [  # first band whose `below` (feet) the height is under; the last one has no `below`
    {"below": 5000, "colour": [255, 120, 0]},
    {"below": 20000, "colour": [60, 220, 0]},
    {"below": 33000, "colour": [0, 190, 255]},
    {"colour": [90, 90, 255]},
]


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass(deg):
    return COMPASS[int((deg % 360) / 22.5 + 0.5) % 16]


class AircraftSource:
    """Fetches aircraft lists from URLs (cached for `min_interval` s) and normalises items from either source."""

    def __init__(self, log=print, min_interval=0.9):
        self.log = log
        self.min_interval = min_interval
        self.cache = {}  # url -> (time, aircraft list)
        self.warned = set()

    def fetch(self, url, headers=None, timeout=2.0):
        now = time.monotonic()
        cached = self.cache.get(url)
        if cached and now - cached[0] < self.min_interval:
            return cached[1]
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=timeout) as r:
                aircraft = json.load(r).get("aircraft", [])
            self.warned.discard(url)
        except Exception as err:
            if url not in self.warned:
                self.warned.add(url)
                self.log(f"{url}: can't read aircraft: {err}", level="WARNING")
            aircraft = cached[1] if cached else []
        self.cache[url] = (now, aircraft)
        return aircraft


def altitude(item):
    alt = item.get("alt_baro", item.get("alt_geom", item.get("altitude_ft")))
    if alt == "ground":
        return 0
    return alt if isinstance(alt, (int, float)) else None


def local_reason(p, rules):
    """`interesting` reason when the source doesn't give one (same rules as the ADS-B Overhead app)."""
    if rules is False:
        return None
    rules = rules or {}
    if p["km"] <= rules.get("special_km", 50):
        if p.get("squawk") in SQUAWKS:
            return SQUAWKS[p["squawk"]].lower()
        if p.get("category") == "A7":
            return "helicopter"
    if not p["on_ground"] and p["alt"] is not None and p["alt"] < rules.get("low_ft", 5000) \
            and p["km"] <= rules.get("low_km", 20):
        return "low flyer"
    if p["km"] <= rules.get("overhead_km", 5):
        return "overhead"
    return None


_COAST = {}  # (path, home, range, width, height) -> list of pixels


def coastline_pixels(path, home, range_km, width, height, log=print):
    """Pixels of a GeoJSON coastline (LineString / MultiLineString / Polygon outlines, lon/lat) projected onto the
    radar: home in the middle, `range_km` to the radar's radius. Cached; the file is read once."""
    key = (path, home, range_km, width, height)
    if key in _COAST:
        return _COAST[key]
    pixels = set()
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError) as err:
        log(f"coastline {path}: {err}", level="WARNING")
        _COAST[key] = []
        return []
    features = data.get("features", [data]) if isinstance(data, dict) else []
    lines = []
    for feature in features:
        geom = feature.get("geometry", feature)
        kind, coords = geom.get("type"), geom.get("coordinates", [])
        if kind == "LineString":
            lines.append(coords)
        elif kind in ("MultiLineString", "Polygon"):
            lines.extend(coords)
        elif kind == "MultiPolygon":
            for poly in coords:
                lines.extend(poly)
    cx, cy = width // 2, height // 2
    scale = (min(width, height) // 2 - 2) / float(range_km)
    kx = math.cos(math.radians(home[0])) * 111.32 * scale
    ky = 110.574 * scale

    def project(pt):
        return cx + (pt[0] - home[1]) * kx, cy - (pt[1] - home[0]) * ky

    for line in lines:
        for a, b in zip(line, line[1:]):
            (x0, y0), (x1, y1) = project(a), project(b)
            steps = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
            for k in range(steps + 1):
                x, y = int(round(x0 + (x1 - x0) * k / steps)), int(round(y0 + (y1 - y0) * k / steps))
                if 0 <= x < width and 0 <= y < height:
                    pixels.add((x, y))
    _COAST[key] = sorted(pixels)
    return _COAST[key]


def normalise(items, cfg, home, max_age=15):
    """Aircraft as dicts with km, bearing, alt, nearest first."""
    planes = []
    for it in items or []:
        if not isinstance(it, dict) or it.get("seen_pos", 0) > max_age:
            continue
        if "lat" in it and "lon" in it and home:
            km = distance_km(home[0], home[1], it["lat"], it["lon"])
            brg = bearing_deg(home[0], home[1], it["lat"], it["lon"])
        elif "km" in it and "bearing" in it:
            km, brg = float(it["km"]), float(it["bearing"])
        else:
            continue
        p = {"flight": (it.get("flight") or it.get("callsign") or it.get("hex", "")).strip().upper(),
             "hex": it.get("hex", ""), "km": km, "bearing": brg, "alt": altitude(it),
             "on_ground": it.get("alt_baro") == "ground", "track": it.get("track"), "gs": it.get("gs"),
             "category": it.get("category"), "squawk": it.get("squawk"),
             "route": it.get("route", ""), "type": it.get("type", "")}
        p["reason"] = it["interesting"] if "interesting" in it else local_reason(p, cfg.get("alert_rules"))
        planes.append(p)
    planes.sort(key=lambda p: p["km"])
    return planes


def band_colour(alt, cfg):
    if alt is None:
        return tuple(cfg.get("colours", {}).get("ground", DEFAULT_COLOURS["ground"]))
    for band in cfg.get("altitude_colours", DEFAULT_BANDS):
        if "below" not in band or alt < band["below"]:
            return tuple(band["colour"])
    return (200, 200, 200)


def height_text(p):
    if p["on_ground"]:
        return "GND"
    return f"{int(p['alt'])}FT" if p["alt"] is not None else "-"


def kind(p):
    t = p.get("type") or ""
    return t.upper() if t and len(t) <= 10 else KINDS.get(p.get("category") or "", "")


def render_aircraft(cfg, planes, width=64, height=64, mdi=None, night=False, now=None, home=None, log=print):
    """Draw one aircraft screen. `cfg` is the screen's `aircraft:` options; `planes` from `normalise`; `home`
    (lat, lon) is only needed for a radar `coastline`."""
    now = time.time() if now is None else now
    colours = dict(DEFAULT_COLOURS, **{k: v for k, v in cfg.get("colours", {}).items()})
    col = {k: tuple(v) for k, v in colours.items()}
    c = Canvas(width, height)
    style = cfg.get("style", "radar")
    if style == "alert":
        hot = [p for p in planes if p["reason"]]
        if hot:
            draw_alert(c, cfg, hot[0], col, mdi, flash=cfg.get("flash", True) and not night, now=now)
            return c.px
        style = "nearest"
    if style == "radar":
        if cfg.get("coastline") and home:
            for x, y in coastline_pixels(cfg["coastline"], home, float(cfg.get("range_km", 100)), width, height, log):
                c.put(x, y, col["coast"])
        draw_radar(c, cfg, planes, col)
    elif style == "board":
        draw_board(c, cfg, planes, col)
    else:
        draw_nearest(c, cfg, planes, col, mdi, now)
    return c.px


def icon(c, mdi, name, x, y, size, colour):
    coverage = mdi.coverage(name, size) if mdi else None
    if coverage:
        draw_mdi(c, coverage, x, y, colour)


# 5 x 5 arrowheads for north and north-east (H: head, full colour; S: shaft, dimmer); the other six headings are
# these turned by 90 degree steps. Centred on the aircraft's position.
ARROW_N = ["..H..", ".HHH.", "H.S.H", "..S..", "..S.."]
ARROW_NE = ["..HHH", "...HH", "..S.H", ".S...", "S...."]
SHAFT = 0.45
MARKERS = ("arrow", "line", "tick")


def arrow_sprite(track):
    """{(dx, dy): brightness} for a 5 x 5 arrowhead pointing along `track` (degrees), snapped to 8 headings."""
    k = int(round(track / 45.0)) % 8
    out = {}
    for y, row in enumerate(ARROW_N if k % 2 == 0 else ARROW_NE):
        for x, ch in enumerate(row):
            if ch != ".":
                dx, dy = x - 2, y - 2
                for _ in range(k // 2):  # turn 90 degrees clockwise (screen y points down)
                    dx, dy = -dy, dx
                out[(dx, dy)] = 1.0 if ch == "H" else SHAFT
    return out


def radar_marker(cfg, count):
    """Marker style for this frame: `marker` (arrow, line or tick), or `line` once more than `line_above` aircraft
    are on the radar (0 or null turns the fallback off)."""
    marker = cfg.get("marker", "arrow")
    if marker not in MARKERS:
        marker = "arrow"
    above = cfg.get("line_above", 12)
    if marker == "arrow" and above and count > above:
        marker = "line"
    return marker


def draw_marker(c, marker, track, x, y, colour):
    """One aircraft at (x, y). `arrow`: 5 x 5 arrowhead on 8 headings; `line`: 5 pixels along the track, white
    nose, full-colour body, fading tail; `tick`: 2 x 2 dot with 2 dim pixels ahead. No track: a 2 x 2 dot."""
    if track is None or marker == "tick":
        if track is not None:
            t = math.radians(track)
            for s in (2, 3):
                c.put(int(round(x + 0.5 + s * math.sin(t))), int(round(y + 0.5 - s * math.cos(t))),
                      tuple(v // 2 for v in colour))
        for dx in (0, 1):
            for dy in (0, 1):
                c.put(x + dx, y + dy, colour)
    elif marker == "line":
        t = math.radians(track)
        sx, sy = math.sin(t), -math.cos(t)
        nose = tuple(int(v + (255 - v) * 0.8) for v in colour)
        for s, f in ((-3, 0.12), (-2, 0.3), (-1, 0.6), (0, 1.0)):
            c.put(int(math.floor(x + 0.5 + s * sx)), int(math.floor(y + 0.5 + s * sy)),
                  tuple(int(v * f) for v in colour))
        c.put(int(math.floor(x + 0.5 + sx)), int(math.floor(y + 0.5 + sy)), nose)
    else:
        for (dx, dy), f in arrow_sprite(track).items():
            c.put(x + dx, y + dy, tuple(int(v * f) for v in colour))


def draw_radar(c, cfg, planes, col):
    w, h = c.w, c.h
    cx, cy = w // 2, h // 2
    radius = min(w, h) // 2 - 2
    range_km = float(cfg.get("range_km", 100))
    scale = radius / range_km
    for ring in cfg.get("rings_km", [range_km / 4, range_km / 2, range_km]):
        r = ring * scale
        steps = max(32, int(2 * math.pi * r * 2))
        for k in range(steps):
            t = 2 * math.pi * k / steps
            c.put(int(round(cx + r * math.sin(t))), int(round(cy - r * math.cos(t))), col["ring"])
    shown = [p for p in planes if p["km"] <= range_km]
    marker = radar_marker(cfg, len(shown))
    for p in reversed(shown):  # nearest drawn last, on top
        rr = p["km"] * scale
        x = int(round(cx + rr * math.sin(math.radians(p["bearing"]))))
        y = int(round(cy - rr * math.cos(math.radians(p["bearing"]))))
        colour = band_colour(p["alt"], cfg)
        if p["reason"]:  # interesting: a box round it, drawn first so the marker is never hidden under it
            for k in range(-3, 4):
                for dx, dy in ((k, -3), (k, 3), (-3, k), (3, k)):
                    c.put(x + dx, y + dy, col["marker"])
        draw_marker(c, marker, p["track"], x, y, colour)
    c.put(cx, cy, col["house"])
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        c.put(cx + dx, cy + dy, tuple(v // 3 for v in col["house"]))
    if cfg.get("show_count", True):
        draw_text(c, str(len(shown)), 0, 0, col["text"])
    if cfg.get("show_range", True):
        label = tuple(min(255, v * 2) for v in col["ring"])
        draw_text(c, f"{int(range_km)}", 0, h - 5, label)
        draw_text(c, "KM", w - text_width("KM"), h - 5, label)


def draw_nearest(c, cfg, planes, col, mdi, now):
    w = c.w
    if not planes:
        draw_text(c, "NO AIRCRAFT", (w - text_width("NO AIRCRAFT")) // 2, 29, col["text"])
        return
    p = planes[0]
    icon(c, mdi, "mdi:helicopter" if p["category"] == "A7" else "mdi:airplane", 0, -1, 11, col["accent"])
    draw_text(c, "NEAREST", 13, 2, col["text"])
    draw_text(c, p["flight"][:10], 0, 11, col["label"], TEXT)
    line = " ".join(x for x in (kind(p), p["route"]) if x)
    draw_text(c, line[:16], 0, 21, col["text"])
    km = p["km"]
    x = draw_text(c, f"{km:.1f}" if km < 100 else f"{km:.0f}", 0, 29, col["accent"], TEXT, scale=2)
    draw_text(c, "KM", x + 1, 38, col["accent"])
    icon(c, mdi, ARROWS[int(p["bearing"] / 45 + 0.5) % 8], w - 11, 30, 11, col["label"])
    draw_text(c, height_text(p), 0, 47, band_colour(p["alt"], cfg))
    if p["gs"] is not None:
        speed = f"{int(round(p['gs']))}KT"
        draw_text(c, speed, w - text_width(speed), 47, col["text"])
    for x in range(w):
        c.put(x, 55, (35, 35, 35))
    others = planes[1:1 + int(cfg.get("ticker_count", 5))]
    if others:  # the others, one at a time: changes every `page_seconds`
        q = others[int(now // float(cfg.get("page_seconds", 3))) % len(others)]
        text = " ".join(x for x in (q["flight"], f"{q['km']:.0f}KM", compass(q["bearing"])) if x)
        draw_text(c, text[:16], 0, 58, col["ticker"])


def draw_board(c, cfg, planes, col):
    y = 1
    for p in planes[:4]:
        draw_text(c, p["flight"][:8], 0, y, col["label"])
        right = p["route"] or kind(p)
        right = right[:16 - min(8, len(p["flight"])) - 1]
        draw_text(c, right, c.w - text_width(right), y, col["text"])
        info = f"{p['km']:.0f}KM {compass(p['bearing'])} {height_text(p)}"
        draw_text(c, info[:16], 0, y + 7, band_colour(p["alt"], cfg))
        y += 16


def draw_alert(c, cfg, p, col, mdi, flash, now):
    w, h = c.w, c.h
    phase = int(now) % 2 if flash else 0
    edge = col["accent"] if phase == 0 else tuple(v // 3 for v in col["accent"])
    for i in range(max(w, h)):
        for t in (0, 1):
            c.put(i, t, edge), c.put(i, h - 1 - t, edge), c.put(t, i, edge), c.put(w - 1 - t, i, edge)
    title = (p["reason"] or "").upper()[:15]
    draw_text(c, title, (w - text_width(title)) // 2, 4, col["accent"] if phase == 0 else col["label"])
    icon(c, mdi, "mdi:helicopter" if p["category"] == "A7" else "mdi:airplane", (w - 20) // 2, 11, 20,
         col["accent"] if phase == 0 else col["label"])
    name = p["flight"][:10]
    draw_text(c, name, (w - text_width(name, TEXT)) // 2, 33, col["label"], TEXT)
    alt = height_text(p)
    draw_text(c, alt, (w - text_width(alt)) // 2, 43, band_colour(p["alt"], cfg))
    where = f"{p['km']:.0f}KM {compass(p['bearing'])}"
    draw_text(c, where, (w - text_width(where)) // 2, 51, col["text"])
