"""Jungle screen: an animated jungle (swaying vines, swinging and climbing monkeys, a snake on a bough, parrots and
toucans flying through, butterflies). No entities needed.

The animals are random: on every visit each one gets a random look, side, speed and path.

Pure Python, no dependencies. Everything is a function of the time `t` (seconds), so a frame can be drawn on demand
and the animation is smooth at any `frame_rate`. At night the jungle is drawn still.
"""

import math

from ...utils.canvas import Canvas

EYE = (10, 10, 20)

# --- Monkeys -----------------------------------------------------------------------------------------------------
# Swinging monkey, facing right, hanging by one hand (the top of column 6). m fur, f face, e eye, b belly,
# r the free arm while it reaches for the next vine, d the free arm while it hangs down, t/u the tail (two frames).
MONKEY = [
    "......m......",
    "......m......",
    "..mmm.m..r...",
    ".mfffmm.r....",
    "ffefefmr.....",
    ".mfffmmm.....",
    "..mmmmmm...t.",
    "..mbbmmd..t.u",
    "..mbbmmd.t.u.",
    "..mmmmmmtuu..",
    ".mm...mm.....",
    ".m.....m.....",
]
MONKEY_HAND = 6

# Climbing monkey, side on, facing the trunk on its right, two poses (hand over hand).
CLIMBER = [
    [
        "..mmm..m.",
        ".mmfff.m.",
        ".mmfefmm.",
        ".mmfffm..",
        "..mmmm...",
        "t.mmbmmmm",
        "t.mmbm...",
        "t.mmmm.m.",
        ".tmm.mmm.",
        "..t......",
    ],
    [
        "..mmm....",
        ".mmfff...",
        ".mmfefmmm",
        ".mmfffm..",
        "..mmmm.m.",
        ".tmmbmmm.",
        "t.mmbm...",
        "t.mmmmmmm",
        "t.mm.....",
        ".t.mm....",
    ],
]

# (fur, belly, face): golden tamarin, capuchin, red howler, silver langur.
MONKEY_LOOKS = [
    ((255, 140, 10), (255, 190, 60), (255, 215, 150)),
    ((170, 95, 35), (240, 210, 150), (255, 220, 170)),
    ((215, 60, 20), (255, 120, 40), (255, 200, 150)),
    ((185, 185, 200), (240, 240, 250), (255, 205, 170)),
]

MONKEY_SLOT = 9.5   # each monkey swings across once per slot, with a new look, direction and tempo
CLIMB_SLOT = 19.0
VINE_TOP = 4
# Two rows ("lanes") of swing vines: (vine length, x of the first vine). Vines are 16 px apart, and a swing ends
# exactly where the next vine's swing starts, so the monkey hands over from vine to vine.
LANES = ((14, -8), (21, 0))
VINE_GAP = 16

# --- Birds -------------------------------------------------------------------------------------------------------
# Facing right, three wing positions (up, level, down). b body, w wing, t tail, h head, c cheek/bib, e eye, k beak,
# j beak tip.
BIRDS = {
    "macaw": [
        ["....ww......", "....www.....", "ttt.bwwwhh..", "..tttbbbcek.", ".....bbbb.k.", "............", "............"],
        ["............", "............", "ttt.wwwwhh..", "..tttwwwcek.", ".....bbbb.k.", "............", "............"],
        ["............", "............", "ttt.bbbbhh..", "..tttbbbcek.", ".....wwwb.k.", ".....www....", "......ww...."],
    ],
    "toucan": [
        ["...ww.......", "...www......", "tt.bwwhh....", ".ttbbbhekkkj", "...bbbcckkj.", "............", "............"],
        ["............", "............", "tt.wwwhh....", ".ttwwwhekkkj", "...bbbcckkj.", "............", "............"],
        ["............", "............", "tt.bbbhh....", ".ttbbbhekkkj", "...wwwcckkj.", "...www......", "....ww......"],
    ],
    "small": [
        ["..ww....", "..ww....", "t.bwhh..", ".tbbcek.", "........", "........"],
        ["........", "........", "t.wwhh..", ".tbbcek.", "........", "........"],
        ["........", "........", "t.bbhh..", ".twwcek.", "..ww....", "........"],
    ],
}
# Looks: body, wing, tail, head, cheek, beak, beak tip.
BIRD_LOOKS = {
    "macaw": [
        ((255, 30, 30), (30, 90, 255), (255, 210, 0), (255, 30, 30), (255, 255, 255), (230, 230, 200), (60, 60, 60)),
        ((20, 110, 255), (255, 210, 0), (20, 110, 255), (20, 110, 255), (255, 255, 255), (70, 70, 90), (60, 60, 60)),
        ((40, 220, 60), (255, 60, 40), (30, 120, 255), (255, 220, 0), (255, 255, 255), (230, 200, 160), (60, 60, 60)),
    ],
    "toucan": [
        ((40, 40, 110), (70, 70, 160), (255, 40, 40), (40, 40, 110), (255, 255, 255), (255, 150, 0), (255, 30, 30)),
        ((40, 40, 110), (70, 70, 160), (255, 255, 255), (40, 40, 110), (255, 230, 0), (120, 230, 40), (255, 60, 0)),
    ],
    "small": [
        ((255, 220, 0), (255, 120, 0), (255, 120, 0), (255, 220, 0), (255, 255, 255), (255, 80, 0), (0, 0, 0)),
        ((0, 220, 255), (0, 110, 255), (0, 110, 255), (0, 220, 255), (255, 255, 255), (255, 200, 0), (0, 0, 0)),
        ((255, 80, 180), (170, 60, 255), (170, 60, 255), (255, 80, 180), (255, 255, 255), (255, 220, 0), (0, 0, 0)),
    ],
}
BIRD_COUNT = 3
BIRD_SLOT = 9.0

# --- Snake -------------------------------------------------------------------------------------------------------
# (body, band, belly side) colours.
SNAKE_LOOKS = [
    ((60, 255, 40), (255, 240, 0)),      # green tree python
    ((255, 40, 30), (255, 230, 0)),      # coral snake
    ((255, 200, 0), (255, 90, 0)),       # yellow boa
    ((0, 220, 200), (255, 255, 255)),    # turquoise
    ((255, 110, 200), (140, 40, 255)),   # pink
]
SNAKE_SLOT = 17.0
SNAKE_LEN = 22

# --- Scenery -----------------------------------------------------------------------------------------------------
LEAF = ((0, 120, 35), (10, 165, 45), (0, 85, 30), (95, 205, 40))
VINE = ((35, 175, 40), (15, 120, 30))
VINE_LEAF = (90, 200, 40)
BARK = ((84, 50, 24), (60, 35, 17))
MOSS = (40, 120, 30)
BOUGH = ((150, 96, 44), (112, 68, 30), (74, 44, 20))
FERN = ((20, 190, 60), (0, 135, 40), (110, 220, 50))
FLOWERS = ((255, 60, 150), (255, 220, 0), (255, 70, 30), (200, 90, 255))
BUTTERFLY = ((255, 235, 60), (90, 200, 255), (255, 130, 220), (255, 150, 30))


def scale(colour, k):
    return tuple(min(255, int(v * k)) for v in colour)


def rand(*key):
    """A repeatable pseudo-random number in [0, 1) for `key`, so a frame depends only on the time."""
    h = 2166136261
    for part in key:
        for ch in str(part):
            h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    return (h ^ (h >> 15)) / 4294967296.0


def pick(items, r):
    return items[int(r * len(items)) % len(items)]


def backdrop(x, y, t):
    """Misty green light between the trees: brightest mid-height, with slow slanting sunbeams."""
    g = math.exp(-((y - 26) / 21.0) ** 2)
    col = (int(3 + 9 * g), int(26 + 44 * g), int(22 + 26 * g))
    if y < 52 and math.sin((x + y * 0.55) * 0.21 + math.sin(t * 0.35) * 0.6) > 0.78:
        col = (int(col[0] * 1.5 + 8), int(col[1] * 1.35 + 6), int(col[2] * 1.15))
    return col


def bough_y(x):
    return 46 + int(round(1.6 * math.sin(x * 0.085 + 0.4)))


def draw_sprite(c, rows, palette, x0, y0, direction, anchor=0, shear=0.0):
    """Draw `rows` with its column `anchor` at x0. `shear` leans the sprite: each row down shifts by that many px."""
    for gy, row in enumerate(rows):
        dx = int(round(shear * gy))
        for gx, ch in enumerate(row):
            col = palette.get(ch)
            if col is not None:
                c.put(x0 + (gx - anchor) * direction + dx, y0 + gy, col)


def draw_vine(c, x0, length, angle, sway, i, taut=False):
    """A hanging vine from (x0, VINE_TOP): leaning by `angle`, its tip bending by `sway` px, with small leaves."""
    sa, ca = math.sin(angle), math.cos(angle)
    for k in range(int(length) + 1):
        f = k / max(1.0, length)
        x = int(round(x0 + sa * k + (0 if taut else sway * f * f)))
        y = int(round(VINE_TOP + ca * k))
        c.put(x, y, VINE[(k // 2 + i) % 2])
        if k % 5 == 3 and k > 4 and (not taut or k < length - 3):
            c.put(x + (1 if (k // 5 + i) % 2 else -1), y, VINE_LEAF)
    if not taut:                                      # a little leaf tuft at the loose end
        c.put(int(round(x0 + sa * length + sway)) - 1, int(round(VINE_TOP + ca * length)) + 1, VINE_LEAF)
        c.put(int(round(x0 + sa * length + sway)) + 1, int(round(VINE_TOP + ca * length)) + 1, VINE[0])


def monkey_visit(i, slot, seed):
    r = lambda *k: rand(seed, "monkey", i, slot, *k)  # noqa: E731
    return {
        "look": MONKEY_LOOKS[(int(r("look") * 2) * 2 + i) % len(MONKEY_LOOKS)],
        "direction": 1 if r("dir") < 0.5 else -1,
        "swing": 1.0 + r("swing") * 0.4,              # seconds per vine
        "start": r("start") * 0.6,
    }


def bird_visit(i, slot, seed):
    r = lambda *k: rand(seed, "bird", i, slot, *k)  # noqa: E731
    kind = ("macaw", "toucan", "macaw", "small")[int(r("kind") * 4)]
    return {
        "kind": kind,
        "look": pick(BIRD_LOOKS[kind], r("look")),
        "direction": 1 if r("dir") < 0.5 else -1,
        "speed": 9.0 + r("speed") * 7.0,              # 9-16 px/s: 2-3 px a frame at 5 fps
        "start": r("start") * 2.5,
        "height": 9 + r("height") * 27,
        "wander": (0.5 + r("wf") * 0.9, 1.0 + r("wa") * 3.0, r("wp") * 6.3),
    }


def render_jungle(cfg, width=64, height=64, t=0.0, night=False):
    """Pixels for a `jungle:` screen."""
    cfg = cfg or {}
    c = Canvas(width, height)
    if night:
        t = 0.0
    seed = cfg.get("seed", 0)
    tick = int(t * 5 + 0.001)                         # animation step for flapping, tongues, tails

    # Backdrop: misty light, sunbeams and the dim trunks of far-off trees.
    for y in range(height):
        for x in range(width):
            c.put(x, y, backdrop(x, y, t))
    for a, b, k in ((13, 15, 0.62), (27, 28, 0.72), (38, 41, 0.6), (49, 50, 0.74)):
        for x in range(a, b + 1):
            for y in range(height):
                c.put(x, y, scale(backdrop(x, y, t), k if x != a else k + 0.12))

    # The bough the snake lives on, with a couple of hanging twigs.
    for x in range(width):
        y = bough_y(x)
        c.put(x, y, BOUGH[0] if (x * 5) % 9 else BOUGH[1])
        c.put(x, y + 1, BOUGH[1])
        c.put(x, y + 2, BOUGH[2])
    for x0, n in ((20, 4), (34, 6), (45, 3)):
        for k in range(n):
            sway = int(round(math.sin(t * 1.1 + x0) * k * 0.25))
            c.put(x0 + sway, bough_y(x0) + 3 + k, VINE[k % 2])
        c.put(x0 + sway + 1, bough_y(x0) + 2 + n, VINE_LEAF)

    # Snake: slithers along the bough from behind one trunk to the other, a wave running down its body.
    slot, into = divmod(t + SNAKE_SLOT * 0.3, SNAKE_SLOT)
    r = lambda *k: rand(seed, "snake", int(slot), *k)  # noqa: E731
    body, band = pick(SNAKE_LOOKS, r("look"))
    sdir = 1 if r("dir") < 0.5 else -1
    travelled = into * (width + SNAKE_LEN - 8) / SNAKE_SLOT
    head = (2 + travelled) if sdir > 0 else (width - 3 - travelled)
    for s in range(SNAKE_LEN - 1, -1, -1):
        x = int(round(head - sdir * s))
        wave = math.sin(s * 0.62 - t * 4.2)
        y = bough_y(x) - 2 + int(round(wave * 1.5 * min(1.0, s / 4.0))) - max(0, 3 - s)   # the neck rears up
        col = band if s > 2 and s % 5 < 2 else body
        if s >= SNAKE_LEN - 3:                        # thin tail
            c.put(x, y + 1, col)
            continue
        c.put(x, y, col)
        c.put(x, y + 1, scale(col, 0.72))
    hx = int(round(head))
    hy = bough_y(hx) - 5
    for dx, dy, col in ((1, -1, body), (2, -1, body), (1, 0, body), (2, 0, body), (3, 0, body),
                        (1, 1, scale(body, 0.72)), (2, 1, scale(body, 0.72)), (2, -1, EYE)):
        c.put(hx + dx * sdir, hy + dy, col)
    if tick % 3 != 1 and not night:                   # tongue flick
        c.put(hx + 4 * sdir, hy + 1, (255, 40, 60))
        if tick % 3 == 0:
            c.put(hx + 5 * sdir, hy + 2 * (tick % 2), (255, 40, 60))

    # Near trunks: a slim one on the left, a broad one on the right (the climbing monkey's).
    for x in range(width):
        for y in range(height):
            left = x <= 4 + (1 if y > 50 else 0) + (1 if y > 58 else 0)
            right = x >= 54 - (1 if y > 50 else 0) - (1 if y > 58 else 0)
            if not (left or right):
                continue
            ridge = (x + (y // 9)) % 4
            col = BARK[1] if ridge == 0 and y % 9 else BARK[0]
            if (x * 7 + y * 11) % 37 == 0:
                col = MOSS
            if (left and x == 4 + (y > 50) + (y > 58)) or (right and x == 54 - (y > 50) - (y > 58)):
                col = BARK[1]                         # shaded edge
            c.put(x, y, col)

    # Monkeys and their vines. Each monkey owns a lane of vines and swings along it like a pendulum, handing over
    # from vine to vine; a vine leans in just before it is grabbed and swings on, dying down, after it is let go.
    monkeys = []
    count = int(cfg.get("monkeys", len(LANES)))
    for lane, (length, first) in enumerate(LANES):
        anchors = list(range(first, width + 9, VINE_GAP))
        theta0 = math.asin(VINE_GAP / 2.0 / length)
        v = into = None
        if lane < count:
            slot, into = divmod(t + lane * MONKEY_SLOT / max(1, count) + MONKEY_SLOT * 0.36, MONKEY_SLOT)
            v = monkey_visit(lane, int(slot), seed)
        for n, ax in enumerate(anchors):
            angle, taut = 0.0, False
            if v:
                order = n if v["direction"] > 0 else len(anchors) - 1 - n
                rel = into - v["start"] - order * v["swing"]
                if 0 <= rel < v["swing"]:
                    angle, taut = -v["direction"] * theta0 * math.cos(math.pi * rel / v["swing"]), True
                    hx = int(round(ax + math.sin(angle) * length))
                    hy = int(round(VINE_TOP + math.cos(angle) * length))
                    monkeys.append((v, hx, hy, angle, rel / v["swing"]))
                elif -0.4 < rel < 0:
                    angle = -v["direction"] * theta0 * ((rel + 0.4) / 0.4) ** 2
                elif rel >= v["swing"]:
                    dt = rel - v["swing"]
                    angle = v["direction"] * theta0 * math.exp(-dt * 0.8) * math.cos(dt * 4.4)
            sway = math.sin(t * 1.2 + ax * 0.7 + lane) * 1.6
            draw_vine(c, ax, length, angle, sway, n + lane, taut)

    # Long lianas that just sway, for depth.
    for i, (x0, length) in enumerate(((10, 30), (37, 34), (51, 24))):
        for k in range(length):
            f = k / length
            x = int(round(x0 + math.sin(t * 0.9 + i * 2 + k * 0.12) * f * 2.4))
            c.put(x, VINE_TOP + k, scale(VINE[(k // 3 + i) % 2], 0.6))
            if k % 6 == 4:
                c.put(x + (1 if (k // 6 + i) % 2 else -1), VINE_TOP + k, scale(VINE_LEAF, 0.6))

    # Climbing monkey on the side of the right trunk: hand over hand, two px a pull, up or down.
    slot, into = divmod(t + CLIMB_SLOT * 0.42, CLIMB_SLOT)
    r = lambda *k: rand(seed, "climb", int(slot), *k)  # noqa: E731
    fur, belly, face = pick(MONKEY_LOOKS, r("look"))
    step = int(into / 0.4)                            # one pull every 0.4 s
    if step * 2 < height + 14:
        up = r("dir") < 0.6
        y = (height + 1 - step * 2) if up else (-12 + step * 2)
        pal = {"m": fur, "f": face, "b": belly, "e": EYE, "t": scale(fur, 0.8)}
        draw_sprite(c, CLIMBER[step % 2], pal, 46, y, 1)

    # Birds: each slot one flies across with a random look, height and speed; slower ones are further back.
    flock = []
    birds = int(cfg.get("birds", BIRD_COUNT))
    for i in range(birds):
        slot, into = divmod(t + i * BIRD_SLOT / max(1, birds) + BIRD_SLOT * 0.3, BIRD_SLOT)
        v = bird_visit(i, int(slot), seed)
        frames = BIRDS[v["kind"]]
        sw = len(frames[0][0])
        travelled = (into - v["start"]) * v["speed"]
        if travelled < 0 or travelled > width + sw:
            continue
        x = int(travelled) - sw if v["direction"] > 0 else width - int(travelled) + sw - 1
        freq, amp, phase = v["wander"]
        y = int(round(v["height"] + math.sin(into * freq + phase) * amp))
        flap = (0, 1, 2, 1)[(tick + i) % 4]
        if flap == 2:
            y -= 1                                    # the body lifts on the downstroke
        flock.append((v["speed"], frames[flap], v["look"], x, y, v["direction"]))
    for speed, rows, look, x, y, direction in sorted(flock, key=lambda b: b[0]):
        k = 0.72 + 0.28 * (speed - 9.0) / 7.0
        pal = {ch: scale(col, k) for ch, col in zip("bwthckj", look)}
        pal["e"] = EYE
        draw_sprite(c, rows, pal, x, y, direction)

    # The swinging monkeys, leaning with the vine; the free arm reaches for the next vine late in the swing.
    for v, hx, hy, angle, p in monkeys:
        fur, belly, face = v["look"]
        pal = {"m": fur, "f": face, "b": belly, "e": EYE}
        pal["r" if p > 0.55 else "d"] = fur
        pal["t" if (tick // 2) % 2 else "u"] = scale(fur, 0.8)
        if night:
            pal["t"] = scale(fur, 0.8)
        draw_sprite(c, MONKEY, pal, hx, hy - 1, v["direction"], MONKEY_HAND, math.tan(angle) * 0.55)

    # Canopy: a leafy ceiling with a ragged, gently rustling lower edge, and a few flowers.
    for x in range(width):
        depth = 5.5 + 2.0 * math.sin(x * 0.45 + 1) + 1.6 * math.sin(x * 1.13 + 2) + 0.7 * math.sin(t * 0.9 + x * 0.35)
        for y in range(int(round(depth)) + 1):
            col = LEAF[int(rand("leaf", x // 2 + y % 2, y // 2 + (x // 3) % 2) * 3)]
            if rand("hi", x, y) < 0.09:
                col = LEAF[3]
            if y >= int(round(depth)):
                col = LEAF[2]
            c.put(x, y, col)
    for i, (x, y) in enumerate(((7, 2), (22, 4), (30, 1), (45, 3), (58, 2))):
        c.put(x, y, FLOWERS[i % len(FLOWERS)])
        c.put(x + 1, y, scale(FLOWERS[i % len(FLOWERS)], 0.7))

    # Undergrowth: ferns that sway at the tips, with flowers, in front of everything.
    for x in range(width):
        top = height - 3 - int(1.4 + 1.4 * math.sin(x * 0.7) + 0.8 * math.sin(x * 0.31 + 2))
        for y in range(top, height):
            c.put(x, y, FERN[1] if (x + y * 2) % 5 else scale(FERN[1], 0.6))
    for i, (x0, h, lean) in enumerate(((3, 7, 1), (9, 9, -1), (12, 6, 1), (19, 8, 1), (24, 5, -1), (30, 9, -1),
                                       (33, 7, 1), (40, 6, -1), (44, 9, 1), (50, 7, -1), (54, 8, 1), (60, 9, -1))):
        for k in range(h):
            f = k / h
            x = int(round(x0 + lean * f * f * h * 0.55 + math.sin(t * 1.4 + i) * f * 1.3))
            c.put(x, height - 2 - k, FERN[2] if k == h - 1 else FERN[(k + i) % 2])
            if k % 2 and 1 < k < h - 1:               # leaflets either side of the frond
                c.put(x - 1, height - 2 - k, FERN[0])
                c.put(x + 1, height - 2 - k, FERN[1])
    for i, (x, y) in enumerate(((16, 58), (27, 60), (37, 58), (47, 60))):
        col = FLOWERS[(i + 1) % len(FLOWERS)]
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            c.put(x + dx, y + dy, col)
        c.put(x, y, (255, 255, 200))

    # Butterflies: bright specks wandering about, wings opening and closing.
    for i in range(int(cfg.get("butterflies", 2))):
        r = lambda *k: rand(seed, "fly", i, *k)  # noqa: E731
        x = int(round(width / 2 + math.sin(t * (0.21 + 0.1 * r("a")) + r("b") * 6.3) * 24 + math.sin(t * 1.7 + i) * 2))
        y = int(round(40 + i * 9 + math.sin(t * (0.5 + 0.2 * r("c")) + r("d") * 6.3) * 6 + math.sin(t * 2.3 + i) * 1.5))
        col = pick(BUTTERFLY, r("col", int(t // 30)))
        c.put(x, y, (255, 255, 255))
        if (tick + i) % 2 or night:
            c.put(x - 1, y - 1, col)
            c.put(x + 1, y - 1, col)
            c.put(x - 1, y, col)
            c.put(x + 1, y, col)
        else:
            c.put(x, y - 1, col)

    return c.px
