"""Surf screen: a surfer riding a breaking wave, seen side-on. No entities needed.

The wave peels to the right: whitewater on the left, the curl, then the clean face sloping away to the shoulder.
Every `ride_seconds` is one ride: the surfer paddles in from the right, pops up, drops in and carves up and down the
face (spray off the top turns, a wake behind), then either kicks out over the shoulder or wipes out (the board flies,
the whitewater swallows them) and the next ride starts with the paddle back out.

cfg keys (all optional):
  wave_style    "barrel" (default): a big hollow wave with a tube the surfer tucks into mid-ride;
                "rolling": a gentle swell, long cruising turns on a longboard;
                "storm": a dark, choppy sea with rain and lightning, big and messy, more wipeouts.
  wave_size     0.6 to 1.4, default 1.0: how tall the wave is.
  sky           "auto" (default: "day", or "storm" for the storm wave), "day", "sunset", "night" or "storm":
                the palette of the sky and the water. `time_of_day` is accepted as another name for it.
  surfer        "auto" (default: picked per ride from the seed), "sandy", "dark", "red" or "silver": hair and skin.
  wetsuit       "auto" (default: picked per ride) or a colour: a name (red, orange, yellow, lime, green, cyan,
                blue, purple, pink, white, black), "#rrggbb" or [r, g, b].
  board         "auto" (default: picked per ride) or a colour, as for `wetsuit`.
  wipeouts      0 to 1, default 0.35 (0.6 for "storm"): the share of rides that end in a wipeout.
  ride_seconds  default 22: the length of one ride, paddle-out included (minimum 12).
  seed          default 0: a different run of rides.

All art is original. Pure Python, no dependencies. Everything is a function of the time `t` (seconds), so any frame
can be drawn on demand. At night one still frame (mid-ride) is drawn.
"""

import math

from ...utils.canvas import Canvas

STYLES = {
    # height px at size 1, x of the curl, length of the lip, how fast the shoulder falls away, carve tempo, carve reach
    "barrel": {"height": 39, "curl": 19, "lip": 13, "power": 1.5, "tempo": 2.6, "reach": 0.34},
    "rolling": {"height": 22, "curl": 13, "lip": 0, "power": 1.1, "tempo": 1.5, "reach": 0.28},
    "storm": {"height": 35, "curl": 17, "lip": 5, "power": 1.3, "tempo": 3.3, "reach": 0.38},
}
BASE = 55             # y of the trough in front of the wave
HORIZON = 24

SKIES = {
    "day": {"sky": ((20, 105, 255), (150, 220, 255)), "far": (0, 75, 200), "lit": (130, 255, 215),
            "mid": (0, 185, 200), "deep": (0, 85, 185), "fore": (0, 60, 170), "glint": (90, 180, 255),
            "foam": (255, 255, 255), "shade": (165, 220, 255), "tube": (0, 55, 105)},
    "sunset": {"sky": ((55, 20, 120), (255, 125, 45)), "far": (125, 40, 110), "lit": (255, 205, 110),
               "mid": (235, 90, 105), "deep": (95, 30, 135), "fore": (65, 20, 105), "glint": (255, 160, 80),
               "foam": (255, 238, 215), "shade": (255, 160, 150), "tube": (60, 15, 80)},
    "night": {"sky": ((3, 5, 30), (15, 28, 85)), "far": (5, 20, 75), "lit": (120, 225, 255),
              "mid": (20, 90, 195), "deep": (8, 30, 105), "fore": (5, 15, 65), "glint": (90, 150, 255),
              "foam": (220, 235, 255), "shade": (105, 140, 235), "tube": (3, 10, 45)},
    "storm": {"sky": ((22, 26, 40), (75, 85, 100)), "far": (20, 52, 62), "lit": (160, 215, 180),
              "mid": (40, 118, 110), "deep": (15, 58, 74), "fore": (10, 42, 58), "glint": (125, 165, 165),
              "foam": (238, 242, 238), "shade": (140, 168, 175), "tube": (8, 30, 40)},
}
SURFERS = {                                           # hair, skin
    "sandy": ((255, 225, 90), (255, 190, 140)),
    "dark": ((45, 28, 22), (165, 105, 65)),
    "red": ((255, 95, 30), (255, 208, 175)),
    "silver": ((225, 230, 240), (225, 160, 120)),
}
COLOURS = {"red": (255, 40, 40), "orange": (255, 140, 0), "yellow": (255, 235, 0), "lime": (160, 255, 30),
           "green": (30, 220, 70), "cyan": (0, 230, 255), "blue": (40, 90, 255), "purple": (170, 70, 255),
           "pink": (255, 60, 170), "white": (255, 255, 255), "black": (25, 25, 35)}
WETSUITS = ("pink", "red", "black", "lime", "purple", "blue")
BOARDS = ("yellow", "white", "orange", "pink", "lime", "red")

# The surfer, facing right. h hair, s skin, w wetsuit.
STAND = ["..hh...", "..hs...", "s.ww..s", ".swwws.", "..ww...", "..www..", ".ww.ww.", ".s...s."]
CROUCH = ["...hh..", "...hs..", ".swwws.", "s.www.s", ".ww.ww.", ".s...s."]
CHEER = ["s.hh.s.", "s.hs.s.", ".swws..", "..ww...", "..ww...", "..www..", ".ww.ww.", ".s...s."]
PRONE = [".......hh", ".swwwwwhs"]
TUMBLE = [
    ["s....s", ".w..w.", "..ww..", ".hww..", "hs.w..", "....s."],
    ["..s...", ".w..hh", "sww.sh", "..www.", ".w..s.", "s....."],
    [".s....", "..w.sh", "..wwh.", "..ww..", ".w..w.", "s....s"],
    [".....s", ".s..w.", ".www..", "hs.wws", "hh..w.", "...s.."],
]


def scale(colour, k):
    return tuple(min(255, int(v * k)) for v in colour)


def mix(a, b, f):
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


def rand(*key):
    """A repeatable pseudo-random number in [0, 1) for `key`, so a frame depends only on the time."""
    h = 2166136261
    for part in key:
        for ch in str(part):
            h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    return (h ^ (h >> 15)) / 4294967296.0


def noise(a, b, c=0):
    """A cheap repeatable 0..255 for three whole numbers (per-pixel texture)."""
    n = (a * 374761393 + b * 668265263 + c * 2246822519) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return (n ^ (n >> 16)) & 0xFF


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def colour(value, fallback):
    """A cfg colour: a name, "#rrggbb" or [r, g, b]."""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(max(0, min(255, int(v))) for v in value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in COLOURS:
            return COLOURS[v]
        if len(v) == 7 and v[0] == "#":
            try:
                return tuple(int(v[i:i + 2], 16) for i in (1, 3, 5))
            except ValueError:
                pass
    return fallback


def draw_sprite(c, rows, palette, x0, y0, direction=1, shear=0.0):
    """Draw `rows` centred on x0 with its bottom row at y0; `shear` leans it (px per row, towards the top)."""
    w, n = len(rows[0]), len(rows)
    for gy, row in enumerate(rows):
        dx = int(round(shear * (n - 1 - gy)))
        for gx, ch in enumerate(row):
            col = palette.get(ch)
            if col is not None:
                c.put(x0 + (gx - w // 2) * direction + dx, y0 - (n - 1 - gy), col)


# --- The wave ----------------------------------------------------------------------------------------------------
class Wave:
    def __init__(self, style, size, t, width):
        s = STYLES[style]
        self.style, self.t = style, t
        swell = 1.0 + 0.05 * math.sin(t * 0.45) + 0.03 * math.sin(t * 1.1 + 1)
        self.h = h = min(BASE - 8.0, s["height"] * size * swell)
        self.curl = curl = s["curl"] + int(round(1.5 * math.sin(t * 0.6)))
        self.lip = lip = int(round(s["lip"] * min(1.25, max(0.7, size))))
        self.top = []
        span = float(width + 8 - curl - lip)
        for x in range(width + 16):
            if x < curl:                              # the broken part: a churning pile of whitewater
                y = BASE - h * (0.58 + 0.42 * (x / float(curl)) ** 2) + 1.6 * math.sin(x * 0.9 - t * 5.0) + 1
            elif x <= curl + lip:
                y = BASE - h + 0.6 * math.sin((x - curl) * 0.5 + t * 3)
            else:
                u = min(1.0, (x - curl - lip) / span)
                y = BASE - h * (1 - u) ** s["power"]
            if style == "storm":
                y += 1.4 * math.sin(x * 0.55 + t * 3.2) + 1.0 * math.sin(x * 0.23 - t * 2.1)
            elif style == "rolling":
                y += 0.6 * math.sin(x * 0.2 + t * 1.3)
            self.top.append(min(BASE - 1.0, y))
        self.tube = None
        if lip >= 9:                                  # the hollow under the lip
            self.tube = (curl + lip * 0.5, BASE - h * 0.47, lip * 0.7, h * 0.25)

    def y(self, x, f):
        """The y on the face at column x, a share f of the way from the crest (0) to the trough (1)."""
        x = max(0.0, min(len(self.top) - 1.001, x))
        i = int(x)
        top = self.top[i] + (self.top[i + 1] - self.top[i]) * (x - i)
        return top + f * (BASE - top)


def draw_sky(c, sky, pal, t, width, flash):
    px = c.px
    top, bottom = pal["sky"]
    for y in range(HORIZON):
        col = mix(top, bottom, y / float(HORIZON - 1))
        if flash:
            col = mix(col, (235, 240, 255), flash * 0.45)
        px[y * width:(y + 1) * width] = [col] * width
    if sky == "day":
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                if dx * dx + dy * dy <= 17:
                    c.put(51 + dx, 9 + dy, (255, 255, 215) if dx * dx + dy * dy <= 6 else (255, 240, 110))
        for i in range(3):
            cx = int((rand("cloud", i) * 90 + i * 31 - t * (0.8 + 0.3 * i)) % 96) - 14
            cy = 4 + i * 5
            for dx in range(11):
                c.put(cx + dx, cy + 1, (255, 255, 255))
                if 2 <= dx <= 7:
                    c.put(cx + dx, cy, (255, 255, 255))
                if 1 <= dx <= 9:
                    c.put(cx + dx, cy + 2, (200, 230, 255))
    elif sky == "sunset":
        for dy in range(-8, 1):
            for dx in range(-8, 9):
                d = dx * dx + dy * dy
                if d <= 64 and not (dy in (-2, -5) and abs(dx) > 2):
                    c.put(44 + dx, HORIZON + dy, (255, 250, 170) if d <= 25 else (255, 215, 80))
        for i in range(3):
            cx = int((rand("cloud", i) * 90 + i * 31 - t * 0.6) % 100) - 16
            for dx in range(13 - i * 2):
                c.put(cx + dx, 5 + i * 4, (255, 150, 130))
                if 2 < dx < 9:
                    c.put(cx + dx, 4 + i * 4, (255, 190, 150))
    elif sky == "night":
        for i in range(24):
            x, y = int(rand("star", i, "x") * width), int(rand("star", i, "y") * (HORIZON - 3))
            c.put(x, y, scale((225, 232, 255), 0.55 + 0.45 * math.sin(t * (1 + rand("star", i, "f") * 2) + i)))
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                if dx * dx + dy * dy <= 17 and (dx - 2) ** 2 + (dy + 1) ** 2 > 9:
                    c.put(50 + dx, 9 + dy, (240, 244, 255))
    else:                                             # storm: heavy cloud banks
        for x in range(width):
            for band, (y0, amp, speed, col) in enumerate(((0, 4, 3.0, (14, 16, 26)), (6, 3, 1.8, (44, 50, 64)))):
                depth = y0 + 4 + amp * math.sin((x + t * speed) * 0.19 + band) + 2 * math.sin((x + t * speed) * 0.47)
                for y in range(y0, int(depth)):
                    px[y * width + x] = mix(col, (235, 240, 255), flash * 0.35) if flash else col


def render_surf(cfg, width=64, height=64, t=0.0, night=False):
    """Pixels for a `surf:` screen."""
    cfg = cfg or {}
    seed = cfg.get("seed", 0)
    style = cfg.get("wave_style", "barrel")
    if style not in STYLES:
        style = "barrel"
    size = max(0.6, min(1.4, float(cfg.get("wave_size", 1.0))))
    sky = cfg.get("sky", cfg.get("time_of_day", "auto"))
    if sky not in SKIES:
        sky = "storm" if style == "storm" else "day"
    pal = SKIES[sky]
    ride = max(12.0, float(cfg.get("ride_seconds", 22)))
    if night:
        t = ride * 0.5
    c = Canvas(width, height)
    px = c.px
    tick = int(t * 5 + 0.001)
    wave = Wave(style, size, t, width)
    top, curl, lip = wave.top, wave.curl, wave.lip

    # Lightning (storm sky): a flash a few times a minute, with a bolt.
    flash, bolt = 0.0, None
    if sky == "storm" and not night:
        cell, into = divmod(t, 3.5)
        if rand(seed, "bolt", int(cell)) < 0.45 and into < 0.45:
            flash = 1.0 - into / 0.45
            bolt = 30 + int(rand(seed, "boltx", int(cell)) * 30)
    draw_sky(c, sky, pal, t, width, flash)
    if bolt is not None and flash > 0.4:
        bx = bolt
        for y in range(4, HORIZON + 2):
            bx += int(rand(seed, "zig", bolt, y) * 3) - 1
            c.put(bx, y, (255, 255, 255))
            c.put(bx + 1, y, (190, 210, 255))

    # The far sea, the wave and the water in front, a pixel at a time.
    far, lit, mid, deep, fore = pal["far"], pal["lit"], pal["mid"], pal["deep"], pal["fore"]
    foam, shade, glint = pal["foam"], pal["shade"], pal["glint"]
    drift = int(t * 12)
    churn = int(t * 6)
    for x in range(width):
        ytop = int(round(top[x]))
        for y in range(HORIZON, height):
            if y < ytop:                              # far sea behind the wave, with lines of swell
                col = far
                if (y - HORIZON) % 4 == 1 and noise((x + drift // 4) // 5, y) < 110:
                    col = mix(far, glint, 0.55)
                elif sky == "sunset" and abs(x - 44) < 9 - (y - HORIZON) // 2 and noise(x + drift // 3, y) < 120:
                    col = (255, 200, 90)
            elif y < BASE:
                f = (y - ytop) / float(BASE - ytop)
                if x < curl - 2 + f * (9 if not wave.tube else 3):   # whitewater, spilling forward at the foot
                    n = noise((x + churn) // 2, (y + churn // 2) // 2, churn // 3)
                    col = foam if n > 90 else (shade if n > 25 else mix(shade, mid, 0.5))
                    if f > 0.8 and n < 120:
                        col = mix(shade, deep, 0.4)
                else:
                    col = mix(lit, mid, f / 0.28) if f < 0.28 else mix(mid, deep, (f - 0.28) / 0.72)
                    if (x + 2 * y + drift) % 9 == 0 and 0.08 < f < 0.9:   # water drawing up the face
                        col = mix(col, lit, 0.4)
                    if y == ytop:                     # the feathering crest
                        near = x - curl - lip
                        col = foam if near < 10 + 3 * math.sin(t * 2) or noise(x + drift, 7) < 60 else lit
                    elif y == ytop + 1 and x - curl - lip < 5:
                        col = shade
                    if style == "storm" and noise(x + drift, y, churn // 2) < 5:
                        col = foam                    # blown foam
            else:                                     # the flat water in front
                d = y - BASE
                col = mix(deep, fore, min(1.0, d / 4.0))
                if (x + drift + y * 5) % 14 < 4 and d % 3 == 1:
                    col = mix(col, glint, 0.6)
                if x < curl + 6 - d and noise((x + churn) // 2, y, churn // 4) > 120:
                    col = foam if noise(x, y, churn) > 100 else shade   # foam spreading out of the whitewater
                if style == "storm" and noise((x + drift) // 2, y, churn // 3) < 16:
                    col = shade
            if flash and y >= ytop:
                col = mix(col, (255, 255, 255), flash * 0.25)
            px[y * width + x] = col

    # The tube: a dark hollow under the lip, the lip throwing over it, spray off the top.
    if wave.tube:
        cx, cy, rx, ry = wave.tube
        for y in range(int(cy - ry * 1.5), int(cy + ry) + 2):
            for x in range(int(cx - rx * 1.5), int(cx + rx) + 2):
                e = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
                if e <= 1.0:
                    k = 0.55 + 0.45 * (x - (cx - rx)) / (2 * rx)
                    c.put(x, y, mix(scale(pal["tube"], k), mid, max(0.0, (y - cy) / ry) * 0.45))
                elif e <= 1.7 and y < cy + ry * 0.2 and x < cx + rx * 0.75:
                    c.put(x, y, foam if noise(x + churn, y) > 70 else shade)
                elif e <= 1.3 and y < cy and x >= cx + rx * 0.75:
                    c.put(x, y, lit)
        for k in range(5):                            # the curtain falling at the back of the tube
            x = int(cx - rx) + k % 3
            y = int(cy - ry * 0.4) + (churn * 2 + k * 5) % max(1, int(ry * 1.3))
            c.put(x, y, foam)
    for k in range(7 if style != "rolling" else 3):   # spray blowing back off the crest
        x = curl + int(rand("spray", k) * (lip + 8))
        age = (t * 1.6 + rand("spray", k, "p")) % 1.0
        c.put(x - int(age * 6), int(top[max(0, min(width - 1, x))]) - 1 - int(age * (5 if style == "storm" else 3)),
              foam if age < 0.6 else shade)
    for k in range(4):                                # and thrown up by the whitewater
        x = int(rand("splash", k) * max(1, curl - 2))
        age = (t * 1.3 + rand("splash", k, "p")) % 1.0
        c.put(x, int(top[x]) - int(4 * math.sin(age * math.pi)), foam)

    # --- The ride ------------------------------------------------------------------------------------------------
    slot, into = divmod(t, ride)
    slot = int(slot)
    r = lambda *k: rand(seed, "ride", slot, *k)  # noqa: E731
    who = cfg.get("surfer", "auto")
    hair, skin = SURFERS[who] if who in SURFERS else SURFERS[sorted(SURFERS)[int(r("who") * len(SURFERS))]]
    suit = colour(cfg.get("wetsuit"), COLOURS[WETSUITS[int(r("suit") * len(WETSUITS))]])
    board = colour(cfg.get("board"), COLOURS[BOARDS[int(r("board") * len(BOARDS))]])
    if board == suit:
        board = COLOURS["white"] if suit != COLOURS["white"] else COLOURS["yellow"]
    body = {"h": hair, "s": skin, "w": suit}
    chance = cfg.get("wipeouts")
    chance = (0.6 if style == "storm" else 0.35) if chance is None else float(chance)
    wipeout = r("end") < chance
    s = STYLES[style]
    paddle, popup, ending = 4.0, 0.8, 3.0
    t_end = ride - ending
    home = curl + lip + 16 + (4 if style == "rolling" else 0)       # where on the face the carving is centred
    start_x = min(width - 9, home + 9)

    def carve(tau):
        """(x, share down the face, pose) while riding."""
        ph = (tau - paddle - popup) * s["tempo"] * (0.85 + 0.3 * r("tempo"))
        f = 0.47 - s["reach"] * math.cos(ph) * (0.8 + 0.2 * math.sin(ph * 0.37 + r("p") * 6))
        x = home + 6.0 * math.sin(ph * 0.5 + 1.0) + 2.0 * math.sin(ph * 0.23)
        pose = CROUCH if math.sin(ph) > 0.55 else STAND
        if wave.tube and r("tube") < 0.85:            # mid-ride, tuck into the tube for a few seconds
            t0 = paddle + popup + 3.0 + r("tube0") * max(0.5, t_end - paddle - popup - 8.5)
            b = smooth((tau - t0) / 0.8) * smooth((t0 + 4.2 - tau) / 0.8)
            cx, cy, rx, ry = wave.tube
            fx = cx + rx * 0.25 + 1.5 * math.sin(tau * 1.3)
            ff = (cy + ry * 0.75 - wave.y(fx, 0)) / max(1.0, BASE - wave.y(fx, 0))
            x, f = x + (fx - x) * b, f + (ff - f) * b
            if b > 0.4:
                pose = CROUCH
        elif style == "rolling" and math.sin(ph * 0.31 + r("c") * 6) > 0.8:
            pose = CHEER                              # cruising, arms up
        drop = smooth((tau - paddle) / (popup + 0.9))  # dropping in from the top at the start
        x, f = start_x + (x - start_x) * drop, 0.06 + (f - 0.06) * drop
        if tau < paddle + popup:
            pose = CROUCH
        return x, f, pose

    def place(tau):
        x, f, pose = carve(tau)
        return x, wave.y(x, f), pose

    def draw_board(x, y, slope, length=5):
        for i in range(-length, length + 1):
            bx, by = int(round(x + i)), int(round(y + i * slope))
            c.put(bx, by, board if abs(i) != 2 else scale(board, 0.6))
            if i == -length + 1:
                c.put(bx, by + 1, (25, 25, 35))       # the fin

    long_board = 6 if style == "rolling" else 5
    if into < paddle:                                 # paddling in from the right, over the shoulder
        k = smooth(into / paddle)
        x = width + 8 + (start_x - width - 8) * k
        y = wave.y(x, 0.06) + 0.8 * math.sin(t * 3)
        draw_board(x, y, 0.0, long_board)
        draw_sprite(c, PRONE, body, int(round(x)), int(round(y)) - 1, direction=-1)
        c.put(int(round(x)) + (1 if tick % 2 else -2), int(round(y)) + 1, skin)   # the paddling arm
        c.put(int(round(x)) + 6, int(round(y)), foam)
    elif into < t_end or not wipeout:
        if into < t_end:
            x, y, pose = place(into)
            x2, y2, _ = place(into - 0.12)
        else:                                         # kick out: up over the shoulder and away to the right
            x0, f0, pose = carve(t_end)
            k = (into - t_end) / ending
            x = x0 + (width + 10 - x0) * k * k
            f = f0 + (-0.12 - f0) * smooth(k * 2.2)
            y = wave.y(x, f)
            x2, y2 = x - 1, wave.y(x - 1, f0 + (-0.12 - f0) * smooth((k - 0.04) * 2.2))
            pose = CHEER if k > 0.25 else pose
        vy = (y - y2) / 0.12                          # px/s down the face
        slope = max(-0.5, min(0.5, vy / 26.0))
        # The wake: where the board was, carried back along the face.
        if into < t_end:
            for k in range(1, 13):
                wx, wy, _ = place(into - k * 0.09)
                wx -= k * 1.5
                if wx > curl + 1 and into - k * 0.09 > paddle + 0.3:
                    c.put(int(round(wx - 4)), int(round(wy)), foam if k < 8 else shade)
        if into < t_end and wave.y(x, 0) > y - 5 and vy > -4:   # a fan of spray off a top turn
            for k in range(6):
                a = (t * 2.5 + k * 0.17) % 1.0
                c.put(int(x - 4 - a * 7 - k % 2), int(y - 1 - 7 * math.sin(a * math.pi) - k % 3), foam)
        bx, by = int(round(x)), int(round(y))
        draw_board(x, y, slope, long_board)
        draw_sprite(c, pose, body, bx, by - 1, shear=-slope * 0.5)
        c.put(bx - long_board - 1, int(round(y - long_board * slope)), foam)
        c.put(bx - long_board - 2, int(round(y - long_board * slope)) - 1, foam)
    else:                                             # wipeout: thrown off, the board flies, the foam takes them
        x0, y0, _ = place(t_end)
        k = into - t_end
        x = x0 - 14.0 * k
        y = y0 - 9.0 * k + 13.0 * k * k
        floor = wave.y(x, 0.85)
        if y < floor or k < 0.4:
            draw_sprite(c, TUMBLE[int(k * 9) % 4], body, int(round(x)), int(round(y)))
        elif k < 2.4:                                 # a head bobbing in the foam, an arm up
            hx, hy = int(round(x)), int(round(floor + math.sin(t * 5)))
            c.put(hx, hy, skin)
            c.put(hx, hy - 1, hair)
            c.put(hx + 1, hy - 1, hair)
            if tick % 2:
                c.put(hx - 2, hy - 2, skin)
            for dx in (-3, -2, 2, 3):
                c.put(hx + dx, hy + 1, foam)
        bx = x0 + 6.0 * k                             # the board spins up and comes down
        by = y0 - 26.0 * k + 22.0 * k * k
        if by < BASE + 2:
            a = k * 7.0
            for i in range(-long_board, long_board + 1):
                c.put(int(round(bx + i * math.cos(a))), int(round(by + i * math.sin(a))),
                      board if abs(i) != 2 else scale(board, 0.6))
        if k < 0.9:                                   # the splash
            for i in range(10):
                a = 3.5 + i * 0.26
                d = 2 + k * 13
                c.put(int(x0 + math.cos(a) * d * 0.8), int(y0 + math.sin(a) * d * 0.7 + 8 * k * k), foam)

    if sky == "storm" or style == "storm":            # rain, slanting with the wind
        for i in range(34):
            x = int(rand("rain", i, "x") * (width + 20))
            y = (int(rand("rain", i, "y") * height) + int(t * (38 + 20 * rand("rain", i, "v")))) % height
            col = (150, 170, 190) if i % 3 else (95, 115, 140)
            c.put(x - y // 3, y, col)
            c.put(x - y // 3 - (y + 1) // 3 + y // 3, y + 1, col)
    return c.px
