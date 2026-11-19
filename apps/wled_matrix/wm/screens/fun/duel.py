"""Duel screen: a Saturday-night TV arena contest, early-90s style. No entities needed.

Two contenders, red on the left and blue on the right, stand on raised chrome-and-gold podiums in a dark studio
arena and battle with padded sticks (a pole with a pad at each end) to knock each other off. Above them a lighting
rig sweeps red, gold and blue spotlights over a crowd of dots in the stands; a small scoreboard at the top shows
bouts won (red, blue) either side of the bout clock.

Every `BOUT_SECS` is one bout: the contenders pump their sticks to the crowd, trade jabs and swings (blocked with a
clack, or landing with a wobble), until one last hit sends the loser teetering, then off backwards onto the crash
mat; the winner bounces with the stick overhead, the crowd's cameras flash, the scoreboard ticks up. Each bout has
new contenders (skin, hair, build of moves) and every `SERIES` bouts the scores start again.

All art is original; no show's name, logo or people are used. Pure Python, no dependencies. Everything is a function
of the time `t` (seconds), so any frame can be drawn on demand. At night one still frame is drawn.

cfg keys: `seed` (default 0): a different run of bouts.
"""

import math

from ...utils.canvas import Canvas
from ..base import Screen

BOUT_SECS = 20.0
SERIES = 5  # bouts before the scoreboard resets
READY = 2.0  # seconds of showing off before the first move
MOVE = 0.75  # seconds per exchange
PODIUM_Y = 46  # y of the podium tops
MAT_Y = 59
LEFT_X, RIGHT_X = 21, 43
SIZE = 1.5  # the contenders are drawn at this many px per point, as 2 x 2 blocks
STANDS = 27  # y of the hoarding in front of the crowd
RED, BLUE = (255, 35, 45), (40, 110, 255)
GOLD, CHROME = (255, 205, 30), (205, 210, 225)
INK = (15, 10, 25)
SKINS = ((255, 205, 165), (230, 165, 115), (175, 110, 70), (120, 75, 50))
HAIRS = ((255, 225, 90), (60, 35, 25), (255, 110, 40), (25, 20, 30), (235, 235, 245))

DIGITS = {
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
}


def scale(colour, k):
    return tuple(min(255, int(v * k)) for v in colour)


def mix(a, b, f):
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


def add(a, b, k):
    return tuple(min(255, int(a[i] + b[i] * k)) for i in range(3))


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
    n = (a * 374761393 + b * 668265263 + c * 2246822519) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return (n ^ (n >> 16)) & 0xFF


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def bout_plan(seed, bout):
    """The script of a bout: who wins, and each exchange as (attacker 0/1, lands?, swing?)."""
    r = lambda *k: rand(seed, "bout", bout, *k)  # noqa: E731
    winner = 0 if r("winner") < 0.5 else 1
    n = 8 + int(r("moves") * 7)
    moves = []
    for i in range(n - 1):
        moves.append((0 if r("who", i) < 0.5 else 1, r("lands", i) < 0.35, r("swing", i) < 0.4))
    moves.append((winner, True, r("swing", n) < 0.5))
    looks = [
        {
            "skin": SKINS[int(r("skin", s) * len(SKINS))],
            "hair": HAIRS[int(r("hair", s) * len(HAIRS))],
            "tail": r("tail", s) < 0.5,
            "trim": GOLD if r("trim", s) < 0.6 else (255, 255, 255),
        }
        for s in (0, 1)
    ]
    return winner, moves, looks


def scores(seed, bout):
    """Bouts won by (red, blue) in this series before bout `bout`."""
    won = [0, 0]
    for b in range(bout - bout % SERIES, bout):
        won[bout_plan(seed, b)[0]] += 1
    return won


def pose(side, tau, winner, moves):
    """How contender `side` stands at bout time tau: lean (radians, + is backwards), stick angle (radians from
    level, + is far end up), stick offset forward and up, a hop, whether a leg is off the podium, and where they
    are relative to their podium (dx backwards, dy down) once they've fallen."""
    p = {
        "lean": 0.0,
        "angle": 1.05,
        "fwd": 0.0,
        "up": 0.0,
        "hop": 0.0,
        "leg": False,
        "dx": 0.0,
        "dy": 0.0,
        "down": False,
    }
    end = READY + len(moves) * MOVE
    if tau < READY:  # pumping the stick overhead for the crowd
        k = smooth(tau / 0.4) * smooth((READY - tau) / 0.4)
        p["up"] = k * (5 + 1.2 * math.sin(tau * 9 + side * 2))
        p["angle"] = 1.05 * (1 - k)
        p["hop"] = k * max(0.0, math.sin(tau * 9 + side * 2))
        return p
    if tau < end:
        i = int((tau - READY) / MOVE)
        u = (tau - READY - i * MOVE) / MOVE
        attacker, lands, swing = moves[i]
        if side == attacker:
            back, thrust = smooth(u / 0.25) * (1 - smooth((u - 0.25) / 0.12)), smooth((u - 0.25) / 0.14) * (
                1 - smooth((u - 0.5) / 0.4)
            )
            if swing:
                p["angle"] = 1.05 + 0.7 * back - 1.5 * thrust
                p["fwd"], p["up"] = 2.5 * thrust, 2 * back - 1 * thrust
            else:
                p["angle"] = 1.05 * (1 - max(back, thrust))
                p["fwd"], p["up"] = -2 * back + 4.5 * thrust, 0.5 * thrust
            p["lean"] = 0.1 * back - 0.22 * thrust
        else:
            k = smooth((u - 0.15) / 0.2) * (1 - smooth((u - 0.6) / 0.3))
            if lands:
                v = max(0.0, u - 0.4)
                p["lean"] = (0.5 * math.exp(-3.0 * v) * math.sin(v * 16) + 0.22 * math.exp(-4 * v)) if u > 0.4 else 0.0
                p["angle"] = 1.05 + (1.2 * math.exp(-4 * v) if u > 0.4 else 0.0)
                p["leg"] = 0.42 < u < 0.8
            else:  # a block: the stick upright, out in front
                p["angle"] = 1.05 + 0.5 * k
                p["fwd"], p["up"] = 2.0 * k, 1.0 * k
                p["lean"] = 0.08 * smooth((u - 0.38) / 0.1) * (1 - smooth((u - 0.5) / 0.4))
        return p
    v = tau - end
    if side == winner:  # a moment to look, then bouncing with the stick overhead
        k = smooth((v - 0.5) / 0.4)
        p["up"], p["angle"] = 5.5 * k, 1.05 * (1 - k)
        p["hop"] = k * 2.5 * abs(math.sin(v * 6.5))
        return p
    if v < 0.9:  # teetering on the edge
        p["lean"] = 0.25 + 0.3 * v + 0.2 * math.sin(v * 14)
        p["angle"], p["up"], p["leg"] = 1.05 + 0.8 * math.sin(v * 11), 2.0, True
        return p
    w = v - 0.9  # and off, backwards, onto the mat
    drop = MAT_Y - PODIUM_Y
    fall = min(1.0, w / 0.6)
    p["lean"] = 0.75 + (math.pi / 2 - 0.75) * smooth(fall * 1.1)
    p["dx"] = 1.0 * smooth(fall * 1.2)
    p["dy"] = drop * fall * fall
    p["angle"], p["up"] = 1.9, 2.0
    if w > 0.6:  # a little bounce, then flat out
        p["dy"] = drop - max(0.0, 2.0 * math.sin((w - 0.6) * 9) * math.exp(-(w - 0.6) * 4))
        p["down"] = True
        p["leg"] = int(w * 3) % 2 == 0
    return p


def draw_fighter(c, x, y, facing, colour, look, p):
    """Draw a contender with feet at (x, y) facing `facing` (1 right, -1 left). Built as points around the feet,
    y up, then leaned over by p["lean"] (so a fall is the same drawing turned on its back)."""
    skin, hair, trim = look["skin"], look["hair"], look["trim"]
    pts = []
    front = [(2, 0, (255, 255, 255)), (2, 1, skin), (2, 2, skin), (2, 3, skin)]
    if p["leg"]:  # the front foot comes off
        front = [(3, 1, (255, 255, 255)), (3, 2, skin), (2, 3, skin)]
    pts += [(-2, 0, (255, 255, 255)), (-2, 1, skin), (-2, 2, skin), (-2, 3, skin)] + front
    pts += [(dx, 4, colour) for dx in range(-2, 3)]
    for dy in range(5, 9):
        for dx in range(-2, 2):
            pts.append((dx, dy, trim if dy == 5 else (scale(colour, 0.7) if dx == -2 else colour)))
    pts += [
        (-1, 9, skin),
        (0, 9, skin),
        (1, 9, skin),
        (-1, 10, colour),
        (0, 10, skin),
        (1, 10, INK),
        (-1, 11, colour),
        (0, 11, colour),
        (1, 11, colour),
        (-2, 10, hair),
    ]
    if look["tail"]:
        pts += [(-2, 9, hair), (-3, 8, hair)]
    a = p["angle"]
    ca, sa = math.cos(a), math.sin(a)
    sx, sy = 3.0 + p["fwd"], 7.0 + p["up"]
    for hand in (-1.6, 1.6):  # arms: shoulders to the two hands on the stick
        hx, hy = sx + ca * hand, sy + sa * hand
        for k in range(1, 5):
            pts.append((0.5 + (hx - 0.5) * k / 4.0, 8 + (hy - 8) * k / 4.0, skin))
    for k in range(-11, 12):  # the stick: chrome pole, a fat gold pad at each end
        d = k / 2.0
        qx, qy = sx + ca * d, sy + sa * d
        if abs(d) > 3.4:
            for off in (-0.6, 0.6):
                pts.append((qx - sa * off, qy + ca * off, GOLD if abs(d) < 5 else (255, 240, 150)))
        else:
            pts.append((qx, qy, CHROME))
    cl, sl = math.cos(p["lean"]), math.sin(p["lean"])
    ox, oy = x - facing * p["dx"], y + p["dy"] - p["hop"]
    for qx, qy, col in pts:
        rx, ry = (qx * cl - qy * sl) * SIZE, (qx * sl + qy * cl) * SIZE
        bx, by = int(round(ox + facing * rx - 0.5)), int(round(oy - ry - 1))
        c.put(bx, by, col)
        c.put(bx + 1, by, col)
        c.put(bx, by + 1, col)
        c.put(bx + 1, by + 1, col)
    tx, ty = sx + ca * 5.5, sy + sa * 5.5  # where the far end of the stick is
    return ox + facing * (tx * cl - ty * sl) * SIZE, oy - (tx * sl + ty * cl) * SIZE


def render_duel(cfg, width=64, height=64, t=0.0, night=False):
    """Pixels for a `duel:` screen."""
    cfg = cfg or {}
    seed = cfg.get("seed", 0)
    c = Canvas(width, height)
    if night:
        t = READY + MOVE * 2 + MOVE * 0.42
    bout, tau = divmod(t, BOUT_SECS)
    bout = int(bout)
    winner, moves, looks = bout_plan(seed, bout)
    end = READY + len(moves) * MOVE
    won = scores(seed, bout)
    decided = tau >= end + 1.5  # the loser has hit the mat
    if decided:
        won[winner] += 1
    cheer = smooth((tau - end - 1.2) / 0.4) if tau > end else (1 - smooth(tau / READY)) * 0.6
    px = c.px

    # The stands: tiers of dark seats and a crowd of dots; cameras flash, more when someone's off.
    for y in range(height):
        row = (5, 4, 18) if y < STANDS else (16, 12, 44)
        px[y * width : (y + 1) * width] = [row] * width
    beat = int(t * 6)
    for y in range(12, STANDS, 2):
        tier = (y - 12) // 2
        for x in range(tier % 2, width, 2):
            n = noise(x, y, 5)
            if n < 30:
                continue
            col = ((120, 60, 60), (60, 70, 130), (120, 105, 50), (90, 90, 100), (70, 110, 80))[n % 5]
            jump = cheer > 0.3 and noise(x, y, beat // 2) < 110
            if noise(x, y, beat) < 3 + int(cheer * 14):
                col = (255, 255, 255)
            c.put(x, y - (1 if jump else 0), col)
    for x in range(width):  # the hoarding in front of the stands
        px[STANDS * width + x] = GOLD if (x // 4) % 3 else CHROME
        px[(STANDS + 1) * width + x] = (RED, GOLD, BLUE)[(x // 8 + 1) % 3] if x % 8 else INK
        px[(STANDS + 2) * width + x] = scale(GOLD, 0.5)

    # The arena floor, the crash mats, and a pool of light under each podium.
    for y in range(STANDS + 3, height):
        for x in range(width):
            col = (14, 10, 40)
            for cx, tint in ((LEFT_X, RED), (RIGHT_X, BLUE)):
                d = ((x - cx) / 14.0) ** 2 + ((y - 52) / 8.0) ** 2
                if d < 1:
                    col = add(col, tint, 0.22 * (1 - d))
            if y >= MAT_Y + 1:
                col = (60, 50, 110) if (x // 8) % 2 else (72, 62, 128)
            if y == MAT_Y + 1:
                col = GOLD
            px[y * width + x] = col

    # The lighting rig and its beams.
    lamps = ((7, RED), (20, GOLD), (32, (255, 255, 255)), (44, GOLD), (57, BLUE))
    for i, (lx, tint) in enumerate(lamps):
        swing = 0.32 * math.sin(t * (0.9 + 0.13 * i) + i * 1.7) + (0.25 if i < 2 else -0.25 if i > 2 else 0)
        power = 0.11 + 0.1 * cheer + (0.08 if tau < READY else 0)
        for y in range(11, MAT_Y + 1):
            mid = lx + swing * (y - 10)
            half = 1.0 + (y - 10) * 0.1
            for x in range(int(mid - half), int(mid + half) + 1):
                if 0 <= x < width:
                    px[y * width + x] = add(px[y * width + x], tint, power)
    for x in range(width):
        px[9 * width + x] = CHROME if x % 4 else (120, 125, 145)
        if x % 4 == 2:
            px[8 * width + x] = (120, 125, 145)
    for lx, tint in lamps:
        for dx in (-1, 0, 1):
            c.put(lx + dx, 10, (60, 60, 75))
        c.put(lx, 11, mix(tint, (255, 255, 255), 0.5))

    # The scoreboard: red's bouts, the clock, blue's bouts, in a gold frame.
    for y in range(8):
        for x in range(15, 49):
            px[y * width + x] = GOLD if y == 7 or x in (15, 48) else ((30, 26, 10) if x in (25, 38) else (6, 6, 12))
    clock = 30 if tau < READY else max(0, 30 - int((min(tau, end) - READY) * 2))
    flash = decided and int(t * 5) % 2 == 0

    def number(text, x, col):
        for ch in text:
            for gy, row in enumerate(DIGITS[ch]):
                for gx, bit in enumerate(row):
                    if bit == "1":
                        c.put(x + gx, 1 + gy, col)
            x += 4

    for dy in range(1, 6):
        c.put(17, dy, RED)
        c.put(46, dy, BLUE)
    number(str(won[0] % 10), 20, (255, 255, 255) if flash and winner == 0 else (255, 70, 70))
    number("%02d" % clock, 28, (255, 225, 40))
    number(str(won[1] % 10), 41, (255, 255, 255) if flash and winner == 1 else (90, 150, 255))

    # The podiums: chrome columns, gold bands, a lit rim in the contender's colour.
    for cx, tint in ((LEFT_X, RED), (RIGHT_X, BLUE)):
        for x in range(cx - 6, cx + 7):
            c.put(x, PODIUM_Y, (255, 255, 255) if abs(x - cx) < 5 else CHROME)
            c.put(x, PODIUM_Y + 1, tint)
        for y in range(PODIUM_Y + 2, MAT_Y + 1):
            band = (y - PODIUM_Y) % 5 == 0
            for x in range(cx - 3, cx + 4):
                shade = (0.55, 0.8, 1.0, 1.0, 0.8, 0.6, 0.4)[x - cx + 3]
                c.put(x, y, scale(GOLD if band else CHROME, shade))

    # The contenders (the fallen one first, so the winner's stick is on top).
    poses = [pose(s, tau, winner, moves) for s in (0, 1)]
    tips = [None, None]
    for s in sorted((0, 1), key=lambda s: -poses[s]["dy"]):
        tips[s] = draw_fighter(c, (LEFT_X, RIGHT_X)[s], PODIUM_Y - 1, (1, -1)[s], (RED, BLUE)[s], looks[s], poses[s])
    if READY <= tau < end:  # a star where the stick lands or is blocked
        i = int((tau - READY) / MOVE)
        u = (tau - READY - i * MOVE) / MOVE
        if 0.36 <= u < 0.56:
            hx, hy = tips[moves[i][0]]
            hx, hy = int(round(hx)), int(round(hy))
            col = (255, 255, 255) if moves[i][1] else (255, 235, 90)
            d = 2 + int((u - 0.36) * 16)
            for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)) + (
                ((d, d), (-d, -d), (d, -d), (-d, d)) if moves[i][1] else ()
            ):
                c.put(hx + dx, hy + dy, col)
            c.put(hx, hy, (255, 255, 255))
    if tau > end + 1.5 and tau < end + 1.9:  # dust off the mat
        d = int((tau - end - 1.5) * 14)
        lx = (LEFT_X - 12, RIGHT_X + 12)[1 - winner]
        for dx in (-6 - d, -3 - d, 3 + d, 6 + d):
            c.put(lx + dx, MAT_Y - 1 - d // 2, (230, 230, 255))

    k = 1.0 if night else min(1.0, tau / 0.4, (BOUT_SECS - tau) / 0.4)  # lights down between bouts
    if k < 1.0:
        c.px = [scale(p, 0.25 + 0.75 * k) for p in c.px]
    return c.px


class DuelScreen(Screen):
    key = "duel"

    def render(self, width, height, *, night, t, now):
        return render_duel(self.cfg, width, height, t=t, night=night)
