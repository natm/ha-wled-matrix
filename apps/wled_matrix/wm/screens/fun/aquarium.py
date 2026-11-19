"""Aquarium screen: an animated fish tank (fish, swaying weed, rising bubbles, sand). No entities needed.

The fish are random: on every visit each one gets a random shape, colours, side, speed, depth and drift.

Pure Python, no dependencies. Everything is a function of the time `t` (seconds), so a frame can be drawn on demand
(e.g. for the web preview) and the animation is smooth at any `frame_rate`. At night the tank is drawn still.
"""

import math

from ...utils.canvas import Canvas

# Fish sprites, facing right. Letters pick a colour from the fish's palette: b body, s stripe/second colour,
# f fin/tail, e eye (always dark), w highlight. "." is transparent.
SPRITES = {
    "clown": [
        "..ff.....",
        "f.bsbbsb.",
        "ffbsbbsbe",
        "f.bsbbsb.",
        "..ff.....",
    ],
    "tang": [
        "...ss....",
        "f.bbbbbb.",
        "ffbbsbbbe",
        "f.bbbbbb.",
        "...ss....",
    ],
    "small": [
        "f.bbb.",
        "ffbbbe",
        "f.bbb.",
    ],
    "angel": [
        "...s...",
        "..sbs..",
        "f.bbbb.",
        "ffbsbbe",
        "f.bbbb.",
        "..sbs..",
        "...s...",
    ],
}

# Bright colours a fish's body and its stripes/fins are picked from at random.
COLOURS = [(255, 110, 0), (20, 80, 255), (255, 230, 0), (255, 40, 80), (230, 230, 240), (0, 220, 120),
           (170, 60, 255), (0, 200, 255), (255, 150, 200), (255, 60, 0)]

FISH_COUNT = 7
SLOT = 18.0          # each fish gets a new random look and path every visit, one visit per slot of up to 18 s

EYE = (10, 10, 20)
SAND = (150, 120, 60)
SAND_DARK = (110, 85, 40)
WEED = ((0, 150, 40), (0, 110, 30))
BUBBLE = (170, 220, 255)
ROCK = (90, 90, 100)
ROCK_DARK = (60, 60, 70)


def water(y, height):
    """Water colour for row y: lighter near the surface, darker at depth."""
    k = y / max(1, height - 1)
    return (0, int(70 - 50 * k), int(140 - 90 * k))


def scale(colour, k):
    return tuple(int(v * k) for v in colour)


def draw_sprite(c, rows, palette, x0, y0, direction, wag):
    width = len(rows[0])
    for gy, row in enumerate(rows):
        for gx, ch in enumerate(row):
            if ch == ".":
                continue
            if ch == "f" and gx < 2 and wag:      # tail flicks up and down a pixel
                gy2 = gy + (1 if gy < len(rows) // 2 else -1) if gy != len(rows) // 2 else gy
            else:
                gy2 = gy
            colour = EYE if ch == "e" else palette.get(ch, palette["b"])
            x = x0 + (gx if direction > 0 else width - 1 - gx)
            c.put(x, y0 + gy2, colour)


def rand(*key):
    """A repeatable pseudo-random number in [0, 1) for `key`, so a frame depends only on the time."""
    h = 2166136261
    for part in key:
        for ch in str(part):
            h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    return (h ^ (h >> 15)) / 4294967296.0


def visit(i, slot, seed):
    """Random look and path for fish i during one slot: sprite, palette, direction, speed, start, depth, wander."""
    r = lambda *k: rand(seed, i, slot, *k)  # noqa: E731
    sprite = sorted(SPRITES)[int(r("sprite") * len(SPRITES))]
    body = COLOURS[int(r("body") * len(COLOURS))]
    second = COLOURS[int(r("second") * len(COLOURS))]
    if second == body:
        second = (255, 255, 255)
    fin = scale(body, 0.75) if r("fin") < 0.5 else second
    return {
        "sprite": sprite,
        "palette": {"b": body, "s": second, "f": fin},
        "direction": 1 if r("dir") < 0.5 else -1,
        "speed": 4.0 + r("speed") * 7.0,          # 4-11 px/s: a crossing takes ~6-18 s
        "start": r("start") * 5.0,                 # enters 0-5 s into its slot
        "depth": 0.1 + r("depth") * 0.62,          # fraction of the water height
        "wander": (0.3 + r("wf") * 0.8, 1.0 + r("wa") * 4.0, r("wp") * 6.3),  # vertical drift: freq, amplitude, phase
    }


def render_aquarium(cfg, width=64, height=64, t=0.0, night=False):
    """Pixels for an `aquarium:` screen."""
    cfg = cfg or {}
    c = Canvas(width, height)
    if night:
        t = 0.0
    sand_top = height - 6

    # Water, with a few slow light ripples near the surface.
    for y in range(height):
        base = water(min(y, sand_top), sand_top)
        for x in range(width):
            col = base
            if y < 5 and math.sin(x * 0.45 + t * 1.2) + math.sin(x * 0.17 - t * 0.7 + y) > 1.5:
                col = scale(base, 1.45)
            c.put(x, y, col)

    # Sand, with a fixed speckle pattern and a gentle slope.
    for x in range(width):
        top = sand_top + int(1.2 * math.sin(x * 0.12))
        for y in range(top, height):
            c.put(x, y, SAND_DARK if (x * 7 + y * 13) % 11 == 0 else SAND)

    # A rock on the right.
    for dy, (a, b) in enumerate(((49, 55), (47, 57), (46, 58), (45, 59))):
        for x in range(a, b + 1):
            c.put(x, sand_top - 4 + dy, ROCK_DARK if x in (a, b) or dy == 0 else ROCK)

    # Weed: strands that sway, more at the tips.
    for i, (x0, h) in enumerate(((5, 20), (9, 14), (27, 24), (40, 12), (61, 18))):
        for k in range(h):
            sway = math.sin(t * 1.3 + i + k * 0.25) * (k / h) * 2.2
            c.put(int(round(x0 + sway)), sand_top - 1 - k, WEED[(k + i) % 2])

    # Fish: each slot a fish swims in from a random side with a random look, speed, depth and drift; their slots are
    # staggered so they don't all arrive together. Slower fish are further back and drawn first, a little dimmer.
    seed = cfg.get("seed", 0)
    swimmers = []
    for i in range(int(cfg.get("fish", FISH_COUNT))):
        offset = i * SLOT / max(1, int(cfg.get("fish", FISH_COUNT)))
        slot, into = divmod(t + offset, SLOT)
        v = visit(i, int(slot), seed)
        rows = SPRITES[v["sprite"]]
        sw = len(rows[0])
        travelled = (into - v["start"]) * v["speed"]
        if travelled < 0 or travelled > width + sw:
            continue
        x = int(travelled) - sw if v["direction"] > 0 else width - int(travelled)
        freq, amp, phase = v["wander"]
        y = int(round(v["depth"] * (sand_top - len(rows)) + math.sin(into * freq + phase) * amp))
        y = max(1, min(sand_top - len(rows) - 1, y))
        swimmers.append((v["speed"], rows, v["palette"], x, y, v["direction"], int(t * 4 + i) % 2 == 0))
    for speed, rows, palette, x, y, direction, wag in sorted(swimmers, key=lambda f: f[0]):
        pal = {k: scale(col, 0.7 + 0.3 * (speed - 4.0) / 7.0) for k, col in palette.items()}
        draw_sprite(c, rows, pal, x, y, direction, wag and not night)

    # Bubbles rising from the bubbler behind the left weed, wobbling as they go.
    for i in range(5):
        period = 6.0
        phase = ((t + i * period / 5) % period) / period
        y = int(sand_top - 2 - phase * (sand_top - 1))
        x = int(round(15 + math.sin(t * 3 + i * 2) * 1.0 + i % 2))
        c.put(x, y, BUBBLE)
        if i % 2 == 0 and phase > 0.3:                # some bubbles grow as they rise
            c.put(x + 1, y, scale(BUBBLE, 0.6))

    return c.px
