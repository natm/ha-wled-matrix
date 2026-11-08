"""Weather screen: today and tomorrow side by side, from any Home Assistant weather entity's daily forecast.

Each half shows the day's name (today underlined), an animated weather icon, the high in big digits, the low, the
rain and the wind with an arrow pointing the way it blows. The rain and wind units are printed once, between the two
days, rather than in each half.

Pure Python, no dependencies. The forecast is the list `weather.get_forecasts` returns for `type: daily` (dicts with
`datetime`, `condition`, `temperature`, `templow`, `precipitation`, `wind_speed`, `wind_bearing`); the app fetches it
every `forecast_interval` seconds. `t` is a time in seconds and drives the icon animation (sun rays twinkle, rain
falls, mist drifts); at night the app draws a still frame once a second.
"""

import datetime
import math

from wm_render import Canvas
from wm_text import TINY, draw_text, text_width

DAY_NAMES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

GREY = (120, 120, 120)
WHITE = (215, 215, 215)
DIVIDER = (28, 28, 28)
UNDERLINE = (0, 110, 160)
SUN = (255, 196, 0)
RAY = (255, 140, 0)
CLOUD = (215, 222, 235)
CLOUD_SHADE = (120, 132, 150)
CLOUD_DARK = (120, 128, 140)
CLOUD_DARK_SHADE = (70, 76, 86)
FOG = (110, 115, 125)
RAIN = (0, 130, 255)
RAIN_TAIL = (0, 70, 160)
SNOW = (235, 240, 255)
BOLT = (255, 220, 0)
MOON = (235, 225, 160)

# HA weather conditions -> the icon drawn for them
ICON_FOR = {
    "sunny": "sunny", "clear-night": "clear-night", "partlycloudy": "partlycloudy", "cloudy": "cloudy",
    "fog": "fog", "rainy": "rainy", "pouring": "rainy", "snowy": "snowy", "snowy-rainy": "snowy", "hail": "snowy",
    "lightning": "lightning", "lightning-rainy": "lightning", "windy": "cloudy", "windy-variant": "cloudy",
    "exceptional": "cloudy",
}

# Met Office-like temperature colours (degrees C)
TEMP_STOPS = [(-5, (150, 90, 255)), (0, (60, 140, 255)), (5, (0, 200, 220)), (10, (120, 220, 40)),
              (15, (255, 200, 0)), (20, (255, 120, 0)), (25, (230, 30, 0))]

WIND_UNITS = {  # label, factor from km/h
    "mph": ("MPH", 0.621371), "kmh": ("KMH", 1.0), "ms": ("M/S", 1 / 3.6), "kn": ("KN", 0.539957),
}
TO_KMH = {"km/h": 1.0, "mph": 1.609344, "m/s": 3.6, "kn": 1.852, "ft/s": 1.09728}


def r0(v):
    """Round half up, as people expect (2.5 -> 3, -2.5 -> -2)."""
    return int(math.floor(v + 0.5))


def temp_colour(c):
    """Colour for a temperature in degrees C."""
    if c <= TEMP_STOPS[0][0]:
        return TEMP_STOPS[0][1]
    for (t0, c0), (t1, c1) in zip(TEMP_STOPS, TEMP_STOPS[1:]):
        if c <= t1:
            f = (c - t0) / (t1 - t0)
            return tuple(int(c0[i] + (c1[i] - c0[i]) * f) for i in range(3))
    return TEMP_STOPS[-1][1]


def rain_text(mm):
    """Rain in mm: "0", one decimal under 10 ("0.4", "6"), whole numbers from 10."""
    if mm is None:
        return "-"
    if mm < 0.05:
        return "0"
    if mm < 9.95:
        s = f"{mm:.1f}"
        return s[:-2] if s.endswith(".0") else s
    return str(r0(mm))


def wind_value(speed, from_unit="km/h", to_unit="mph"):
    if speed is None:
        return None
    kmh = float(speed) * TO_KMH.get(from_unit, 1.0)
    return kmh * WIND_UNITS.get(to_unit, WIND_UNITS["mph"])[1]


def num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def parse_time(s):
    if isinstance(s, datetime.datetime):
        return s
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def pick_days(forecast, now, count=2):
    """The forecast entries for today and the following days (by local date), at most `count`."""
    today = now.date()
    out = []
    for entry in forecast or []:
        when = parse_time(entry.get("datetime"))
        if when is None:
            continue
        if when.tzinfo and now.tzinfo:
            when = when.astimezone(now.tzinfo)
        if when.date() >= today and all(when.date() != d for d, _ in out):
            out.append((when.date(), entry))
        if len(out) == count:
            break
    return out


class WeatherCanvas(Canvas):
    def put(self, x, y, colour, a=1.0):
        """Put a pixel at float coordinates, blending with what's there by `a` (0..1)."""
        x, y = int(math.floor(x)), int(math.floor(y))
        if 0 <= x < self.w and 0 <= y < self.h and a > 0:
            if a < 1:
                old = self.px[y * self.w + x]
                colour = tuple(int(old[i] * (1 - a) + colour[i] * a) for i in range(3))
            self.px[y * self.w + x] = tuple(int(v) for v in colour)

    def shape(self, inside, x0, y0, x1, y1, colour_at, ss=4):
        """Anti-aliased fill: `inside(x, y)` is tested on ss x ss samples per pixel; colour_at(px, py) the colour."""
        for py in range(int(math.floor(y0)), int(math.ceil(y1)) + 1):
            for px in range(int(math.floor(x0)), int(math.ceil(x1)) + 1):
                n = sum(inside(px + (i + .5) / ss, py + (j + .5) / ss) for i in range(ss) for j in range(ss))
                if n:
                    self.put(px, py, colour_at(px, py), n / ss / ss)

    def hline(self, x0, x1, y, c):
        for x in range(x0, x1 + 1):
            self.put(x, y, c)

    def vline(self, x, y0, y1, c):
        for y in range(y0, y1 + 1):
            self.put(x, y, c)

    def text(self, s, x, y, colour):
        return draw_text(self, s, x, y, colour, TINY)


# ---------------------------------------------------------------- icons ----------------------------------------
def draw_sun(c, cx, cy, r, phase=0):
    c.shape(lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 <= r * r, cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1,
            lambda px, py: SUN)
    for k in range(8):  # rays; alternate rays lengthen with the phase (twinkle)
        a = math.radians(k * 45 + 22.5)
        ln = r + 2.2 + (1.0 if (k + phase) % 2 == 0 else 0)
        for s in (r + 1.6, ln):
            c.put(cx + s * math.cos(a), cy + s * math.sin(a), RAY)


def cloud_inside(x0, y0, w, h):
    """A cloud filling the box (x0, y0, w, h): three bumps on a flat base."""
    circles = [(x0 + w * .30, y0 + h * .62, h * .36), (x0 + w * .55, y0 + h * .42, h * .44),
               (x0 + w * .78, y0 + h * .64, h * .32)]

    def inside(x, y):
        if x0 + w * .12 <= x <= x0 + w * .92 and y0 + h * .55 <= y <= y0 + h * .98:
            return True
        return any((x - cx) ** 2 + (y - cy) ** 2 <= r * r for cx, cy, r in circles)
    return inside


def draw_cloud(c, x0, y0, w, h, light=CLOUD, shade=CLOUD_SHADE):
    def colour(px, py):
        k = (py - y0) / h
        return tuple(int(light[i] * (1 - k * .55) + shade[i] * k * .55) for i in range(3))
    c.shape(cloud_inside(x0, y0, w, h), x0, y0, x0 + w, y0 + h, colour)


def draw_moon(c, cx, cy, r):
    c.shape(lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 <= r * r
            and (x - cx - r * .55) ** 2 + (y - cy + r * .3) ** 2 > (r * .85) ** 2,
            cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1, lambda px, py: MOON)


def draw_icon(c, condition, x, y, w, h, phase=0):
    """A multi-colour icon for an HA weather condition in the box (x, y, w, h); `phase` 0..2 animates it."""
    icon = ICON_FOR.get(condition, "cloudy")
    if icon == "sunny":
        draw_sun(c, x + w / 2, y + h / 2, min(w, h) * .28, phase)
    elif icon == "clear-night":
        draw_moon(c, x + w / 2, y + h / 2, min(w, h) * .36)
        for sx, sy in ((.12, .2), (.85, .15), (.8, .8)):
            if (int(sx * 10) + phase) % 3:
                c.put(x + sx * w, y + sy * h, WHITE)
    elif icon == "partlycloudy":
        draw_sun(c, x + w * .64, y + h * .34, min(w, h) * .22, phase)
        draw_cloud(c, x, y + h * .32, w * .82, h * .66)
    elif icon == "cloudy":
        draw_cloud(c, x + w * .25, y + h * .08, w * .72, h * .6, CLOUD_DARK, CLOUD_DARK_SHADE)
        draw_cloud(c, x, y + h * .32, w * .82, h * .66)
    elif icon in ("rainy", "snowy", "lightning"):
        draw_cloud(c, x, y, w, h * .62, CLOUD_DARK, CLOUD_DARK_SHADE)
        if icon == "lightning":
            for dx, dy in ((0, 0), (-1, 1), (-2, 2), (-1, 2), (0, 2), (-1, 3), (-2, 4)):
                c.put(x + w * .55 + dx, y + h * .66 + dy, BOLT if phase != 1 else RAIN_TAIL)
        for i, dx in enumerate((.25, .5, .75)):
            if icon == "lightning" and i == 1:
                continue
            for k in range(2):
                yy = y + h * .66 + ((phase + i + k * 2) % 3) * 2
                if icon == "snowy":
                    c.put(x + w * dx - k * 2, yy, SNOW)
                else:
                    c.put(x + w * dx - k, yy, RAIN)
                    c.put(x + w * dx - k, yy + 1, RAIN_TAIL)
    elif icon == "fog":
        draw_cloud(c, x + w * .1, y, w * .8, h * .58)
        for i, yy in enumerate((.68, .82, .96)):
            off = ((phase + i) % 3) - 1
            for xx in range(int(x + w * .08) + off, int(x + w * .92) + off):
                c.put(xx, y + h * yy - 1, FOG)


def wind_arrow(c, cx, cy, bearing_from, colour, size=2.6):
    """An arrow pointing the way the wind blows (it comes *from* `bearing_from` degrees, so it points downwind)."""
    a = math.radians(bearing_from + 180)
    dx, dy = math.sin(a), -math.cos(a)
    tip = (cx + dx * size, cy + dy * size)
    tail = (cx - dx * size, cy - dy * size)
    for s in range(0, 11):
        k = s / 10
        c.put(tail[0] + (tip[0] - tail[0]) * k, tail[1] + (tip[1] - tail[1]) * k, colour)
    for side in (-1, 1):  # arrow head
        b = a + math.pi + side * math.radians(40)
        for s in (1, 2):
            c.put(tip[0] + math.sin(b) * s, tip[1] - math.cos(b) * s, colour)


def droplet(c, x, y, colour=RAIN):
    for dx, dy in ((1, 0), (1, 1), (0, 2), (1, 2), (2, 2), (0, 3), (1, 3), (2, 3), (1, 4)):
        c.put(x + dx, y + dy, colour)


def big_temp(c, value, x, y, colour):
    """Whole degrees in 2x digits with a small degree ring; returns the x after it."""
    from wm_glyphs import BIG
    s = str(r0(value))
    for ch in s:
        glyph = BIG[ch]
        for gy, row in enumerate(glyph):
            for gx, bit in enumerate(row):
                if bit == "1":
                    for d in ((0, 0), (1, 0), (0, 1), (1, 1)):
                        c.put(x + gx * 2 + d[0], y + gy * 2 + d[1], colour)
        x += (len(glyph[0]) + 1) * 2
    for dx, dy in ((1, 0), (0, 1), (2, 1), (1, 2)):
        c.put(x + dx, y + dy, colour)
    return x + 3


def big_temp_width(value):
    from wm_glyphs import BIG
    s = str(r0(value))
    return sum((len(BIG[ch][0]) + 1) * 2 for ch in s) + 3


# ---------------------------------------------------------------- the screen -----------------------------------
def animation_phase(cfg, t, night=False):
    """Which of the 3 icon frames shows at time `t`: `animation_speed` frames a second (default 2), still at night
    or with `animate: false`. The frame only changes with this and the forecast, so the app can cache it."""
    if night or not cfg.get("animate", True):
        return 0
    return int(t * float(cfg.get("animation_speed", 2.0))) % 3


def render_weather(cfg, forecast, now, width=64, height=64, t=0.0, night=False, units=None):
    """`cfg` is the screen's `weather:` block, `forecast` the daily list, `now` an aware local datetime.
    `units` = {"temperature": "°C"|"°F", "wind_speed": "km/h"|...} from the weather entity's attributes."""
    units = units or {}
    c = WeatherCanvas(width, height)
    fahrenheit = "F" in str(units.get("temperature", "°C"))
    wind_from = units.get("wind_speed", "km/h")
    wind_to = cfg.get("wind_unit", "mph")
    days = pick_days(forecast, now, 2)
    phase = animation_phase(cfg, t, night)

    def colour_of(temp):
        return temp_colour((temp - 32) / 1.8 if fahrenheit else temp)

    if not days:
        msg = "NO DATA"
        c.text(msg, (width - text_width(msg)) // 2, height // 2 - 3, GREY)
        return c.px

    c.vline(32, 2, 48, DIVIDER)
    for i, (date, d) in enumerate(days):
        x0, cw = (0, 32) if i == 0 else (33, 31)
        label = DAY_NAMES[date.weekday()]
        lw = text_width(label)
        lx = x0 + (cw - lw) // 2
        c.text(label, lx, 1, WHITE if date == now.date() else GREY)
        if date == now.date():
            c.hline(lx, lx + lw - 1, 7, UNDERLINE)
        draw_icon(c, d.get("condition"), x0 + 5, 9, 22, 18, phase)
        hi, lo = num(d.get("temperature")), num(d.get("templow"))
        if hi is not None:
            big_temp(c, hi, x0 + (cw - big_temp_width(hi)) // 2 + 1, 29, colour_of(hi))
        else:
            c.text("-", x0 + cw // 2 - 1, 34, GREY)
        if lo is not None:
            s = f"LO {r0(lo)}°"
            c.text(s, x0 + (cw - text_width(s)) // 2, 45, colour_of(lo))

    # Bottom rows: rain and wind, today's ending left of the centre, tomorrow's starting right of it, and the unit
    # once in the middle (as on a table).
    rain_y, wind_y = 52, 58
    c.text("MM", 32 - text_width("MM") // 2, rain_y, GREY)
    wind_label = WIND_UNITS.get(wind_to, WIND_UNITS["mph"])[0]
    c.text(wind_label, 32 - text_width(wind_label) // 2, wind_y, GREY)
    left_end = {rain_y: 32 - text_width("MM") // 2 - 3, wind_y: 32 - text_width(wind_label) // 2 - 3}
    right_start = {rain_y: 32 + (text_width("MM") + 1) // 2 + 3, wind_y: 32 + (text_width(wind_label) + 1) // 2 + 3}
    for i, (_, d) in enumerate(days):
        rain = rain_text(num(d.get("precipitation")))
        rain_col = RAIN if (num(d.get("precipitation")) or 0) >= 0.05 else WHITE
        w = 4 + text_width(rain)  # droplet (3) + gap + number
        x = left_end[rain_y] - w + 1 if i == 0 else right_start[rain_y]
        droplet(c, x, rain_y, RAIN)
        c.text(rain, x + 4, rain_y, rain_col)

        wind = wind_value(num(d.get("wind_speed")), wind_from, wind_to)
        ws = "-" if wind is None else str(r0(wind))
        w = 8 + text_width(ws)  # arrow (7) + gap + number
        x = left_end[wind_y] - w + 1 if i == 0 else right_start[wind_y]
        bearing = num(d.get("wind_bearing"))
        if bearing is not None:
            wind_arrow(c, x + 3, wind_y + 2.5, bearing, WHITE)
        c.text(ws, x + 8, wind_y, WHITE)
    return c.px
