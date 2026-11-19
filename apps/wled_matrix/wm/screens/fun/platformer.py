"""Platformer screen: a little auto-playing side-scrolling platform game in the 16-bit console style. No entities
needed.

Rusty the fox (orange, purple scarf) runs to the right through an endless run of short stages: he jumps gaps (water
below), hops up and down steps and floating planks, bounces on slimes, clears thorny brambles, ducks under buzzers
and picks up gems and stars. The score is at the top left, the stage progress bar at the top right. Each stage lasts
`STAGE_SECS` and ends at a flag; the next one has a new backdrop (meadow, sunset, moonlight, snow) and a new layout.

All art here is original to this app. Pure Python, no dependencies. Everything is a function of the time `t`
(seconds): the stage is built from (`seed`, stage number), and the fox's position on it follows from the time into
the stage, so any frame can be drawn on demand. At night one still frame is drawn.

cfg keys: `seed` (default 0): a different run of stages.
"""

import math
from bisect import bisect_right

from ...utils.canvas import Canvas

SPEED = 22.0          # px/s the fox runs at (and the world scrolls)
GRAVITY = 180.0       # px/s2: sets how high a jump of a given length goes
STAGE_SECS = 60.0
STAGE_LEN = int(SPEED * STAGE_SECS)
PAD = 40              # world columns kept before x=0
WORLD = STAGE_LEN + 120
GROUND = 52           # y of the top of the ground at its lowest level
HERO_X = 20           # screen x of the fox's middle
FLAG_X = STAGE_LEN - 26
INK = (25, 15, 40)

# name: sky top, sky bottom, mountains, snow cap, hills (2), grass (2), dirt (2), plank (2), cloud, slime
THEMES = [
    {"name": "meadow", "sky": ((30, 120, 255), (140, 215, 255)), "mount": (95, 115, 215), "cap": (240, 245, 255),
     "hill": ((40, 185, 95), (25, 150, 80)), "grass": ((110, 255, 50), (30, 180, 40)),
     "dirt": ((200, 115, 40), (140, 75, 25)), "plank": ((255, 215, 60), (190, 120, 20)), "cloud": (255, 255, 255),
     "slime": (255, 50, 200), "orb": ((255, 245, 120), (255, 255, 220)), "stars": False},
    {"name": "sunset", "sky": ((70, 30, 150), (255, 130, 70)), "mount": (130, 45, 130), "cap": (255, 170, 150),
     "hill": ((95, 40, 110), (70, 28, 90)), "grass": ((255, 215, 40), (220, 120, 20)),
     "dirt": ((150, 60, 50), (100, 35, 40)), "plank": ((120, 240, 255), (30, 130, 190)), "cloud": (255, 180, 170),
     "slime": (60, 255, 120), "orb": ((255, 230, 90), (255, 250, 200)), "stars": False},
    {"name": "moonlight", "sky": ((6, 8, 45), (35, 45, 125)), "mount": (45, 55, 135), "cap": (150, 170, 255),
     "hill": ((18, 75, 105), (12, 55, 85)), "grass": ((50, 240, 190), (20, 140, 130)),
     "dirt": ((120, 70, 175), (80, 40, 125)), "plank": ((255, 170, 60), (170, 90, 20)), "cloud": (70, 85, 170),
     "slime": (255, 70, 110), "orb": ((235, 240, 255), (255, 255, 255)), "stars": True},
    {"name": "snow", "sky": ((60, 150, 255), (200, 235, 255)), "mount": (150, 185, 250), "cap": (255, 255, 255),
     "hill": ((120, 175, 245), (95, 150, 230)), "grass": ((255, 255, 255), (170, 215, 255)),
     "dirt": ((70, 110, 215), (45, 75, 165)), "plank": ((255, 120, 60), (170, 60, 30)), "cloud": (255, 255, 255),
     "slime": (255, 60, 190), "orb": ((255, 245, 150), (255, 255, 230)), "stars": False},
]
NIGHT_THEME = 2

# --- Sprites -----------------------------------------------------------------------------------------------------
# Rusty the fox, facing right. o fur, d darker fur, w cream, k eye/nose, s scarf, t tail, c tail tip.
FOX_BODY = [
    "......o.o.",
    "......ooo.",
    "c....ookoo",
    "ct...oowwk",
    ".tt.ssss..",
    ".ttooooo..",
    "..oooowd..",
]
FOX_BODY_AIR = [                                      # tail streaming out behind
    "......o.o.",
    "......ooo.",
    ".....ookoo",
    ".....oowwk",
    "ctt.ssss..",
    ".cttoooo..",
    "..oooowd..",
]
FOX_LEGS = [
    ["..od..od..", ".od....od."],
    ["..od.od...", "..od..od.."],
    ["...odd....", "...od....."],
    ["..od.od...", ".od...od.."],
]
FOX_LEGS_UP = [".odd..odd.", ".........."]
FOX_LEGS_DOWN = ["..od..od..", "..o...o..."]
FOX = {"o": (255, 130, 10), "d": (200, 75, 0), "w": (255, 240, 200), "k": (20, 10, 30), "s": (190, 70, 255),
       "t": (255, 130, 10), "c": (255, 240, 200)}

SLIME = [
    ["..mmm..", ".mmmmm.", "mwkmwkm", "mmmmmmm", "nmmmmmn"],
    [".......", ".mmmmm.", "mwkmwkm", "mmmmmmm", "nmmmmmn"],
]
SLIME_FLAT = ["mmmmmmmmm", "nmmmmmmmn"]
BRAMBLE = ["r..r..r", ".rpppr.", "rpypypr", ".ppppp.", "rpppppr"]
BRAMBLE_COL = {"r": (255, 45, 45), "p": (120, 35, 150), "y": (255, 240, 0)}
BUZZER = [
    [".ww.ww.", "..w.w..", "ykykyyr", ".ykyy.."],
    [".......", "wwwwww.", "ykykyyr", ".ykyy.."],
]
BUZZER_COL = {"w": (255, 255, 255), "y": (255, 225, 0), "k": (30, 20, 30), "r": (255, 60, 40)}
GEM = ["..x..", ".xgx.", "xgwgx", ".xhx.", "..x.."]
GEM_COLS = ((255, 225, 0), (255, 50, 100), (60, 255, 110), (80, 220, 255))
STAR = ["...x...", "..xgx..", "xxxgxxx", "xggwggx", ".xgggx.", "xggxggx", "xxx.xxx"]
STAR_COL = (255, 235, 30)
CLOUD = ["...www....", ".wwwwwww..", "wwwwwwwwww", ".sssssss.."]

DIGITS = {
    "0": ["111", "101", "101", "101", "111"], "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"], "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"], "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"], "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"], "9": ["111", "101", "111", "001", "111"],
}


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


def tri(x):
    """A triangle wave, 0..1, period 1."""
    x -= math.floor(x)
    return 1 - abs(2 * x - 1)


def draw_sprite(c, rows, palette, x0, y0):
    for gy, row in enumerate(rows):
        for gx, ch in enumerate(row):
            col = palette.get(ch)
            if col is not None:
                c.put(x0 + gx, y0 + gy, col)


# --- The stage ---------------------------------------------------------------------------------------------------
class Stage:
    """One stage: the ground, the planks, what's on it, and the path the fox takes through it.

    `pieces` is the fox's path: (x0, x1, y0, y1, rise). rise 0 is a run along a surface whose top is y0; otherwise
    it's a jump from surface y0 to surface y1 that peaks `rise` px above the straight line between them.
    """

    def __init__(self, seed, number):
        self.number = number
        self.theme = THEMES[number % len(THEMES)]
        self.top = [GROUND] * WORLD                   # y of the top of the ground per world column, None = a gap
        self.pieces, self.items, self.slimes, self.brambles, self.buzzers, self.planks = [], [], [], [], [], []
        self.px, self.py = -PAD, GROUND
        levels, gaps = [(-PAD, GROUND)], []
        r = lambda *k: rand(seed, "stage", number, *k)  # noqa: E731
        x, i, last = 34, 0, ""
        while x < STAGE_LEN - 110:
            i += 1
            h = self.py
            kind = ("gap", "gap", "gap", "slime", "slime", "bramble", "bramble", "plank", "plank", "step", "step",
                    "gems", "gems", "buzzer", "star")[int(r(i, "kind") * 15)]
            if kind == last or (kind == "plank" and h < GROUND - 5):
                kind = "gems" if last != "gems" else "gap"
            last = kind
            if kind == "gems":
                n = 3 + int(r(i, "n") * 3)
                for k in range(n):
                    self.item(x + 4 + 6 * k, h - 6, "gem")
                x += 6 * n + 4
            elif kind == "gap":                       # a gap, sometimes with the far side higher or lower
                w = 9 + int(r(i, "w") * 6)
                dh = (-5, 0, 0, 5)[int(r(i, "dh") * 4)]
                if not GROUND - 10 <= h + dh <= GROUND:
                    dh = 0
                gaps.append((x + 3, x + 3 + w))
                levels.append((x + 3 + w, h + dh))
                self.jump(x, x + w + 6, h + dh)
                for f in (0.3, 0.5, 0.7):
                    gx = int(x + (w + 6) * f)
                    self.item(gx, int(self.path(gx)[0]) - 6, "gem")
                x += w + 6 + 6
            elif kind == "step":
                dh = -5 if h > GROUND - 10 and (h == GROUND or r(i, "dh") < 0.5) else 5
                levels.append((x + 7, h + dh))
                self.jump(x, x + 13, h + dh)
                x += 13 + 5
            elif kind == "slime":                     # jump onto it, bounce off
                xe = x + 14
                self.jump(x, xe, h - 3)
                self.jump(xe, xe + 13, h)
                self.slimes.append((xe, h))
                self.item(xe, h - 4, "stomp")
                self.item(xe + 6, int(self.path(xe + 6)[0]) - 7, "gem")
                x = xe + 13 + 5
            elif kind == "bramble":
                self.brambles.append((x + 8, h))
                self.jump(x, x + 16, h)
                self.item(x + 8, int(self.path(x + 8)[0]) - 6, "gem")
                x += 16 + 5
            elif kind == "plank":                     # up onto a floating plank, along it, and down again
                length = 18 + int(r(i, "len") * 14)
                a, b = x + 13, x + 13 + length
                self.planks.append((a, b, h - 11))
                if r(i, "under") < 0.5:
                    gaps.append((x + 5, b + 4))
                else:
                    for k in range(a + 4, b - 6, 12):
                        self.brambles.append((k + 3, h))
                self.jump(x, a + 4, h - 11)
                for gx in range(a + 8, b - 3, 6):
                    self.item(gx, h - 17, "gem")
                self.jump(b - 2, b + 10, h)
                x = b + 10 + 5
            elif kind == "buzzer":                    # it bobs up just as the fox runs under
                self.buzzers.append((x + 11, h))
                self.item(x + 5, h - 6, "gem")
                self.item(x + 17, h - 6, "gem")
                x += 24
            else:                                     # a big jump for a star
                self.jump(x, x + 18, h)
                self.item(x + 9, int(self.path(x + 9)[0]) - 7, "star")
                x += 18 + 5
            x += 3 + int(r(i, "rest") * 7)
        self.run(WORLD)

        levels.append((WORLD, 0))
        for (a, h), (b, _) in zip(levels, levels[1:]):
            for k in range(a + PAD, min(b + PAD, WORLD)):
                self.top[k] = h
        for a, b in gaps:
            for k in range(a + PAD, b + PAD):
                self.top[k] = None
        self.flag_y = self.top[FLAG_X + PAD]
        self.starts = [p[0] for p in self.pieces]
        self.items.sort()
        self.item_x = [it[0] for it in self.items]
        self.totals, total = [0], 0
        for it in self.items:
            total += {"gem": 1, "stomp": 2, "star": 5}[it[2]]
            self.totals.append(total)

    def run(self, x1):
        if x1 > self.px:
            self.pieces.append((self.px, x1, self.py, self.py, 0.0))
            self.px = x1

    def jump(self, x0, x1, y1):
        self.run(x0)
        rise = GRAVITY * ((x1 - x0) / SPEED) ** 2 / 8
        self.pieces.append((x0, x1, self.py, y1, rise))
        self.px, self.py = x1, y1

    def item(self, x, y, kind):
        self.items.append((x, y, kind, len(self.items)))

    def path(self, x, pieces=None):
        """(y of the surface under the fox's feet, or of his feet in the air; -1 rising, 1 falling, 0 running)."""
        if pieces is None:                            # while building: the newest piece
            x0, x1, y0, y1, rise = self.pieces[-1]
        else:
            x0, x1, y0, y1, rise = self.pieces[max(0, bisect_right(self.starts, x) - 1)]
        if not rise:
            return float(y0), 0
        f = (x - x0) / (x1 - x0)
        return y0 + (y1 - y0) * f - 4 * rise * f * (1 - f), (-1 if (y1 - y0) - 4 * rise * (1 - 2 * f) < 0 else 1)


_stages = {}


def stage_for(seed, number):
    key = (seed, number)
    if key not in _stages:
        if len(_stages) > 3:
            _stages.clear()
        _stages[key] = Stage(seed, number)
    return _stages[key]


# --- Drawing -----------------------------------------------------------------------------------------------------
def draw_backdrop(c, th, cam, t, width, height):
    px = c.px
    top, bottom = th["sky"]
    for y in range(height):
        px[y * width:(y + 1) * width] = [mix(top, bottom, min(1.0, y / 44.0))] * width
    if th["stars"]:
        for i in range(26):
            x, y = int(rand("star", i, "x") * width), 8 + int(rand("star", i, "y") * 26)
            k = 0.55 + 0.45 * math.sin(t * (1 + rand("star", i, "f") * 2) + i)
            c.put(x, y, scale((230, 235, 255), k))
    ox, oy = 50, 15                                   # sun or moon
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            d = dx * dx + dy * dy
            if d <= 18:
                c.put(ox + dx, oy + dy, th["orb"][1] if d <= 6 else th["orb"][0])
    if th["stars"]:                                   # bite out of the moon
        for dy in range(-3, 2):
            for dx in range(0, 4):
                if (dx - 2) ** 2 + (dy + 1) ** 2 <= 5:
                    c.put(ox + dx, oy + dy, mix(top, bottom, (oy + dy) / 44.0))
    for i in range(4):                                # clouds, drifting slowly
        cx = int((rand("cloud", i, "x") * 110 + i * 27 - cam * 0.06 - t * 1.2) % 110) - 16
        cy = 9 + int(rand("cloud", i, "y") * 14)
        draw_sprite(c, CLOUD, {"w": th["cloud"], "s": scale(th["cloud"], 0.78)}, cx, cy)
    for sx in range(width):                           # far mountains, then nearer hills
        wx = sx + cam * 0.12
        m = 15 * tri(wx / 46.0) + 7 * tri(wx / 19.0 + 0.3)
        y0 = int(44 - m)
        for y in range(y0, 46):
            px[y * width + sx] = th["cap"] if (m > 15 and y < y0 + 2 + (sx + int(cam * 0.12)) % 2) else th["mount"]
        wx = sx + cam * 0.3
        y0 = int(41 - 4 * math.sin(wx * 0.085) - 2.5 * math.sin(wx * 0.21 + 1))
        for y in range(y0, height):
            px[y * width + sx] = th["hill"][0] if y < y0 + 2 else th["hill"][1]


def draw_ground(c, st, th, cam, t, width, height):
    px = c.px
    grass, dirt = th["grass"], th["dirt"]
    ripple = int(t * 5)
    for sx in range(width):
        wx = sx + cam
        g = st.top[wx + PAD]
        if g is None:                                 # a gap: water at the bottom
            for y in range(height - 5, height):
                px[y * width + sx] = (30, 90, 255) if y > height - 5 else (
                    (220, 240, 255) if (wx + ripple) % 5 < 2 else (90, 170, 255))
            continue
        edge = st.top[wx + PAD - 1] != g or st.top[wx + PAD + 1] != g
        for y in range(g, height):
            d = y - g
            if d == 0:
                col = grass[0]
            elif d == 1 or (d == 2 and wx % 3 == 0):
                col = grass[1]
            elif edge or (wx * 7 + y * 5) % 13 == 0 or (wx * 3 + y * 11) % 17 == 0:
                col = dirt[1]
            else:
                col = dirt[0]
            px[y * width + sx] = col
    for a, b, y in st.planks:                         # floating planks
        if b - cam < 0 or a - cam >= width:
            continue
        for wx in range(a, b):
            sx = wx - cam
            end = wx in (a, b - 1)
            if not end:
                c.put(sx, y, th["plank"][0])
            c.put(sx, y + 1, th["plank"][0] if (wx - a) % 6 else th["plank"][1])
            c.put(sx, y + 2, th["plank"][1])
            if not end and (wx - a) % 6 == 3:
                c.put(sx, y + 3, scale(th["plank"][1], 0.6))


def draw_decor(c, st, th, cam, width, seed):
    """Bushes, flowers and little trees on level bits of ground (behind everything that moves)."""
    for cell in range((cam - 8) // 9, (cam + width + 8) // 9 + 1):
        wx = cell * 9 + 4
        if not -PAD + 4 <= wx < WORLD - PAD - 4:
            continue
        g = st.top[wx + PAD]
        if g is None or any(st.top[wx + PAD + k] != g for k in (-3, -2, -1, 1, 2, 3)):
            continue
        if any(p[0] - 4 <= wx < p[1] + 4 for p in st.planks):
            continue
        what = rand(seed, "decor", st.number, cell)
        sx = wx - cam
        if what < 0.16:                               # a small round tree
            for k in range(1, 6):
                c.put(sx, g - k, th["dirt"][1])
            for dy in range(-3, 3):
                for dx in range(-3, 4):
                    if dx * dx + dy * dy * 1.6 <= 9.5:
                        c.put(sx + dx, g - 8 + dy, th["grass"][1] if dy > 0 or dx > 1 else th["grass"][0])
        elif what < 0.36:                             # a bush
            for dx in range(-2, 3):
                c.put(sx + dx, g - 1, th["grass"][1])
            for dx in range(-1, 2):
                c.put(sx + dx, g - 2, th["grass"][0] if dx < 1 else th["grass"][1])
        elif what < 0.6:                              # a flower
            c.put(sx, g - 1, th["grass"][1])
            c.put(sx, g - 2, ((255, 90, 170), (255, 255, 255), (255, 200, 0))[int(what * 100) % 3])


def draw_gem(c, x, y, col, tick):
    pal = {"x": INK, "g": col, "w": (255, 255, 255) if tick % 4 < 2 else col, "h": scale(col, 0.7)}
    draw_sprite(c, GEM, pal, x - 2, y - 2)


def draw_number(c, text, x, y, col):
    for ch in text:
        for gy, row in enumerate(DIGITS[ch]):
            for gx, bit in enumerate(row):
                if bit == "1":
                    c.put(x + gx + 1, y + gy + 1, INK)
        for gy, row in enumerate(DIGITS[ch]):
            for gx, bit in enumerate(row):
                if bit == "1":
                    c.put(x + gx, y + gy, col)
        x += 4
    return x


def still_time(seed):
    """A good moment for the night frame: the fox in mid-air over the first gap of stage 0."""
    st = stage_for(seed, 0)
    for x0, x1, _, _, rise in st.pieces:
        if rise and st.top[int((x0 + x1) / 2) + PAD] is None:
            return (x0 + (x1 - x0) * 0.45) / SPEED
    return 5.0


def render_platformer(cfg, width=64, height=64, t=0.0, night=False):
    """Pixels for a `platformer:` screen."""
    cfg = cfg or {}
    seed = cfg.get("seed", 0)
    c = Canvas(width, height)
    if night:
        t = still_time(seed)
    number, into = divmod(t, STAGE_SECS)
    st = stage_for(seed, int(number))
    th = THEMES[NIGHT_THEME] if night else st.theme
    hx = into * SPEED
    cam = int(round(hx)) - HERO_X
    tick = int(t * 5 + 0.001)

    draw_backdrop(c, th, cam, t, width, height)
    draw_decor(c, st, th, cam, width, seed)
    draw_ground(c, st, th, cam, t, width, height)

    # The flag at the end of the stage: it turns gold as the fox passes.
    fx, fy = FLAG_X - cam, st.flag_y
    if -8 < fx < width + 2:
        won = hx >= FLAG_X
        for k in range(1, 15):
            c.put(fx, fy - k, (230, 230, 240) if k % 4 else (150, 150, 170))
        c.put(fx, fy - 15, (255, 235, 30))
        for dx in range(1, 7):
            wave = int(round(math.sin(t * 6 + dx * 0.9) * (dx / 6.0)))
            for dy in range(4 - (dx + 1) // 3 * 0 if dx < 5 else 2):
                c.put(fx + dx, fy - 14 + dy + wave + (1 if dx >= 5 else 0),
                      (255, 225, 30) if won else ((255, 50, 60) if (dx + dy) % 2 else (255, 255, 255)))

    # Things to collect: gone once the fox has reached them, with a sparkle for a moment after.
    for x, y, kind, n in st.items[bisect_right(st.item_x, cam - 6):bisect_right(st.item_x, cam + width + 6)]:
        if kind == "stomp":
            continue
        sx = x - cam
        col = STAR_COL if kind == "star" else GEM_COLS[n % len(GEM_COLS)]
        if x > hx:
            bob = int(round(math.sin(t * 4 + x * 0.5) * 0.6))
            if kind == "star":
                draw_sprite(c, STAR, {"x": INK, "g": col, "w": (255, 255, 255) if tick % 2 else col},
                            sx - 3, y - 3 + bob)
            else:
                draw_gem(c, sx, y + bob, col, tick + n)
        else:
            age = (hx - x) / SPEED
            if age < 0.45:
                d = 2 + int(age * 12)
                for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
                    c.put(sx + dx, y + dy - int(age * 8), (255, 255, 255) if d % 2 else col)
                if kind == "star":
                    for dx, dy in ((d, d), (-d, d), (d, -d), (-d, -d)):
                        c.put(sx + dx * 2 // 3, y + dy * 2 // 3 - int(age * 8), col)

    # Brambles sit still; buzzers bob (and are at the top of their bob when the fox runs under); slimes patrol
    # (and are back at their spot just as the fox lands on them).
    for x, g in st.brambles:
        if -8 < x - cam < width + 8:
            draw_sprite(c, BRAMBLE, BRAMBLE_COL, x - cam - 3, g - 5)
    for x, g in st.buzzers:
        if -8 < x - cam < width + 8:
            dt = (hx - x) / SPEED
            y = g - 17 + 5 * (1 - math.cos(dt * 2.6)) / 2 + (0 if abs(dt) < 0.5 else 3 * (1 - math.cos(dt * 2.6)) / 2)
            bx = x - cam - 3 + int(round(2 * math.sin(dt * 1.7)))
            draw_sprite(c, BUZZER[tick % 2], BUZZER_COL, bx, int(round(y)))
    slime = {"m": th["slime"], "n": scale(th["slime"], 0.6), "w": (255, 255, 255), "k": INK}
    for x, g in st.slimes:
        if -12 < x - cam < width + 12:
            dt = (hx - x) / SPEED
            if dt < 0:
                sx = x - cam - 3 + int(round(5 * math.sin(dt * 2.4)))
                draw_sprite(c, SLIME[int(t * 3) % 2], slime, sx, g - 5)
            elif dt < 0.3:
                draw_sprite(c, SLIME_FLAT, slime, x - cam - 4, g - 2)
            elif dt < 0.6:                            # a puff where it was
                d = 2 + int((dt - 0.3) * 14)
                for dx, dy in ((-d, -1), (d, -1), (-d + 1, -d), (d - 1, -d), (0, -d - 1)):
                    c.put(x - cam + dx, g - 1 + dy, (255, 255, 255))

    # The fox.
    y, air = st.path(hx, st.pieces)
    feet = int(round(y))
    if air < 0:
        rows = FOX_BODY_AIR + FOX_LEGS_UP
    elif air > 0:
        rows = FOX_BODY_AIR + FOX_LEGS_DOWN
    else:
        rows = FOX_BODY + FOX_LEGS[int(hx / 3.0) % 4]
    draw_sprite(c, rows, FOX, HERO_X - 5, feet - 9)
    i = max(0, bisect_right(st.starts, hx) - 1)       # dust where he took off or landed
    x0, x1, y0, y1, rise = st.pieces[i]
    for wx, gy, on in ((x0, y0, True), (st.pieces[i - 1][0] if i else x0, st.pieces[i - 1][2] if i else y0,
                                        bool(i) and st.pieces[i - 1][4] == 0)):
        age = (hx - wx) / SPEED
        if on and 0 <= age < 0.3 and (rise or (i and st.pieces[i - 1][4])) and wx > 0:
            d = 1 + int(age * 12)
            c.put(wx - cam - d, int(gy) - 1 - d // 2, (255, 255, 255))
            c.put(wx - cam + d, int(gy) - 1 - d // 2, (235, 235, 235))

    # Score (top left) and how far through the stage he is (top right).
    for y in range(7):
        for x in range(width):
            c.px[y * width + x] = scale(c.px[y * width + x], 0.3)
    n = bisect_right(st.item_x, hx)
    recent = n and (hx - st.item_x[n - 1]) / SPEED < 0.35
    draw_gem(c, 3, 3, GEM_COLS[0], tick)
    draw_number(c, "%03d" % (st.totals[n] % 1000), 7, 1, (255, 235, 30) if recent else (255, 255, 255))
    a, b = 33, width - 7
    done = a + int((b - a) * min(1.0, hx / FLAG_X))
    for x in range(a, b + 1):
        c.put(x, 3, (255, 130, 10) if x <= done else (90, 90, 110))
    c.put(done, 2, (255, 190, 80))
    c.put(done, 4, (255, 190, 80))
    for dy in range(1, 6):
        c.put(b + 1, dy, (230, 230, 240))
    for dx, dy in ((2, 1), (3, 1), (4, 2), (2, 2), (3, 2), (2, 3), (3, 3)):
        c.put(b + dx, dy, (255, 50, 60))

    k = 1.0 if night else min(1.0, into / 0.5, (STAGE_SECS - into) / 0.5)   # fade between stages
    if k < 1.0:
        c.px = [scale(p, k) for p in c.px]
    return c.px
