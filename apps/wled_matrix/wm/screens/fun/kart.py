"""Kart screen: an auto-playing kart race in the early-90s console style, with a tilted "floor plane" view of the
track receding to a horizon. No entities needed.

Six animal drivers race three laps of a procedurally generated circuit: grey asphalt with red-and-white kerbs and a
chequered start line, striped grass, trees at the trackside, hills and clouds on the horizon that swing round as the
track bends. You ride behind Bolt the hare (the white kart); rivals surge past and drop back. Glowing spark crystals
float over the track. The HUD shows the race position and the lap; each race starts with a light countdown and
ends with a chequered flag and the finishing place, then a new circuit is generated.

Why the tilted plane rather than top-down: at 64 x 64 a top-down track shows only a few car-widths of road, and the
karts become 3-4 px specks; the plane view gives the near road, the player's kart and the closest rivals most of
the screen, the curves read from the road bending away, and the horizon gives the sense of speed.

cfg keys: `seed` (default 0) picks the circuits, rivals and how the race unfolds.

Pure Python, no dependencies. Everything is a function of the time `t` (seconds): each race has a fixed RACE_T
slot, its circuit is generated from a hash of (seed, race) and cached as a small distance map, and the karts'
positions are closed-form functions of time. At night the scene is drawn still.
"""

import math
from functools import lru_cache

from ...utils.canvas import Canvas

HZ = 22              # horizon row
CAM_H = 10.0
FOCAL = 40.0
GRID = 256           # the circuit map is GRID x GRID world units
ROAD = 7.0           # half-width of the asphalt
KERB = 1.6
LAPS = 3
COUNTDOWN = 2.4
DRIVE = 48.0         # seconds of racing
FINISH = 5.0
RACE_T = COUNTDOWN + DRIVE + FINISH
NPTS = 720

# Drivers: (name, kart, helmet, ears/face accent). The first is the player.
DRIVERS = [
    ("hare", (245, 245, 255), (255, 140, 30), (255, 200, 210)),
    ("frog", (40, 210, 60), (255, 230, 40), (40, 210, 60)),
    ("croc", (0, 150, 120), (255, 60, 60), (120, 230, 120)),
    ("owl", (150, 70, 255), (255, 200, 80), (255, 170, 60)),
    ("bot", (60, 170, 255), (200, 210, 230), (255, 60, 60)),
    ("fox", (255, 60, 40), (40, 40, 60), (255, 140, 40)),
]

# Kart, seen from behind. b body, B dark body, h helmet, e ears, w wheels, x exhaust, t tail light.
KART = [
    ".....e....e.....",
    ".....ee..ee.....",
    "......hhhh......",
    ".....hhhhhh.....",
    ".....hhvvhh.....",
    "...bbbbbbbbbb...",
    "wwwbtbBBBBbtbwww",
    "wwwbbbbbbbbbbwww",
    "wwwBbbbbbbbbBwww",
    "www.xx....xx.www",
]
KART_LEAN = [
    "....e....e......",
    "....ee..ee......",
    ".....hhhh.......",
    "....hhhhhh......",
    "....hhvvhh......",
    "...bbbbbbbbbb...",
    "wwwbtbBBBBbtbwww",
    "wwwbbbbbbbbbbwww",
    "wwwBbbbbbbbbBwww",
    "www.xx....xx.www",
]

SKY = ((40, 110, 230), (150, 210, 255))
HILLS = ((60, 150, 90), (40, 120, 70))
MOUNT = (110, 120, 200)
GRASS = ((40, 175, 60), (30, 145, 50))
ASPHALT = ((95, 95, 105), (85, 85, 95))
KERBS = ((240, 30, 30), (250, 250, 250))
HAZE = (140, 190, 225)
TREE = ((20, 120, 40), (50, 170, 60), (90, 55, 25))
CRYSTAL = ((80, 240, 255), (255, 255, 255))

FONT = {
    "0": ["111", "101", "101", "101", "111"], "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"], "3": ["111", "001", "011", "001", "111"],
    "4": ["101", "101", "111", "001", "001"], "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"], "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"], "9": ["111", "101", "111", "001", "111"],
    "L": ["100", "100", "100", "100", "111"], "P": ["110", "101", "110", "100", "100"],
    "/": ["001", "001", "010", "100", "100"], "S": ["111", "100", "111", "001", "111"],
    "T": ["111", "010", "010", "010", "010"], "N": ["1001", "1101", "1011", "1001", "1001"],
    "D": ["110", "101", "101", "101", "110"], "R": ["110", "101", "110", "101", "101"],
    "H": ["101", "101", "111", "101", "101"],
}


def rand(*key):
    """A repeatable pseudo-random number in [0, 1) for `key`."""
    h = 2166136261
    for part in key:
        for ch in str(part):
            h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    return (h ^ (h >> 15)) / 4294967296.0


def mix(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


@lru_cache(maxsize=3)
def circuit(seed, race):
    """A closed circuit: NPTS equally spaced centreline points, its length, and a distance map around it."""
    r = lambda *k: rand(seed, race, *k)  # noqa: E731
    harm = [(k, (r("a", k) - 0.5) * (40.0 / k), r("p", k) * 6.3) for k in (2, 3, 4, 5)]
    dense = []
    for i in range(2000):
        a = i / 2000.0 * 2 * math.pi
        rad = 82 + sum(amp * math.sin(k * a + ph) for k, amp, ph in harm)
        dense.append((128 + rad * math.cos(a) * 1.05, 128 + rad * math.sin(a) * 0.95))
    cum = [0.0]
    for i in range(1, len(dense) + 1):
        (x0, y0), (x1, y1) = dense[i - 1], dense[i % len(dense)]
        cum.append(cum[-1] + math.hypot(x1 - x0, y1 - y0))
    length = cum[-1]
    pts, j = [], 0
    for i in range(NPTS):
        s = i * length / NPTS
        while cum[j + 1] < s:
            j += 1
        f = (s - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
        (x0, y0), (x1, y1) = dense[j], dense[(j + 1) % len(dense)]
        pts.append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
    # Distance map: for each cell near the track, the distance to the centreline and the nearest point's index.
    reach = int(ROAD + KERB + 3)
    dist2 = [9801.0] * (GRID * GRID)
    near = [0] * (GRID * GRID)
    for i in range(0, NPTS, 2):
        px, py = pts[i]
        for gy in range(max(0, int(py) - reach), min(GRID, int(py) + reach + 2)):
            dy2 = (gy + 0.5 - py) ** 2
            row = gy * GRID
            for gx in range(max(0, int(px) - reach), min(GRID, int(px) + reach + 2)):
                d2 = (gx + 0.5 - px) ** 2 + dy2
                if d2 < dist2[row + gx]:
                    dist2[row + gx] = d2
                    near[row + gx] = i
    dist = [math.sqrt(v) for v in dist2]
    # Trackside trees and floating crystals.
    trees = []
    for i in range(0, NPTS, 9):
        if r("tree", i) < 0.55:
            side = 1 if r("side", i) < 0.5 else -1
            off = ROAD + KERB + 4 + r("off", i) * 10
            x, y, nx, ny = frame_at(pts, length, i * length / NPTS)
            tx, ty = x + nx * off * side, y + ny * off * side
            gx, gy = int(tx), int(ty)
            if 0 <= gx < GRID and 0 <= gy < GRID and dist[gy * GRID + gx] > ROAD + KERB + 2:
                trees.append((tx, ty))
    crystals = []
    for k in range(10):
        s = (k + 0.5) * length / 10
        lane = (r("lane", k) - 0.5) * ROAD
        for j in range(3):
            crystals.append((s + j * 4, lane))
    return {"pts": pts, "length": length, "dist": dist, "near": near, "trees": trees, "crystals": crystals}


def frame_at(pts, length, s):
    """(x, y, normal x, normal y) on the centreline at arclength s (normal points to the right of travel)."""
    n = len(pts)
    f = (s % length) / length * n
    i = int(f) % n
    u = f - int(f)
    (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
    x, y = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
    (ax, ay), (bx, by) = pts[(i - 2) % n], pts[(i + 3) % n]
    dx, dy = bx - ax, by - ay
    m = math.hypot(dx, dy) or 1.0
    return x, y, -dy / m, dx / m


def heading(pts, length, s):
    n = len(pts)
    f = (s % length) / length * n
    i = int(f)
    (ax, ay), (bx, by) = pts[(i - 3) % n], pts[(i + 4) % n]
    return math.atan2(by - ay, bx - ax)


def curvature(pts, length, s):
    a, b = heading(pts, length, s - 6), heading(pts, length, s + 6)
    d = (b - a + math.pi) % (2 * math.pi) - math.pi
    return d / 12.0


def progress(seed, race, tr, length):
    """Arclength the player has driven at race time tr, and each rival's lead over the player (in units)."""
    speed = LAPS * length / (DRIVE - 0.75)
    d = max(0.0, tr - COUNTDOWN)
    if d < 1.5:                                   # pulling away from the grid
        s = speed * d * d / 3.0
    elif d < DRIVE:
        s = speed * (d - 0.75)
    else:                                         # over the line, slowing down
        e = min(d - DRIVE, FINISH)
        s = LAPS * length + speed * (e - e * e / (2 * FINISH))
    leads = []
    for k in range(1, len(DRIVERS)):
        r = lambda *q: rand(seed, race, "rival", k, *q)  # noqa: E731
        grid = ((k + 1) // 2) * 7 * (1 if k % 2 else -1) * (0.6 + 0.3 * r("g"))
        amp = 14 + 24 * r("amp")
        w = 0.06 + 0.1 * r("w")
        ph = r("ph") * 6.3
        lead = grid + (amp * (math.sin(w * d + ph) - math.sin(ph))) * min(1.0, d / 4.0)
        leads.append(lead)
    return s, leads


def lateral(seed, race, k, s, c):
    """Lateral position (right of the centreline) of driver k: a racing line inside the curves, plus a wander."""
    curv = curvature(c["pts"], c["length"], s + 12)
    lane = (rand(seed, race, "lane", k) - 0.5) * 6
    v = -curv * 140 + lane + 1.5 * math.sin(s * 0.05 + k)
    return max(-ROAD + 2, min(ROAD - 2, v))


def text(c, s, x, y, col, size=1, shadow=None):
    for ch in s:
        g = FONT.get(ch, [])
        for gy, row in enumerate(g):
            for gx, b in enumerate(row):
                if b == "1":
                    for dy in range(size):
                        for dx in range(size):
                            if shadow:
                                c.put(x + gx * size + dx + 1, y + gy * size + dy + 1, shadow)
                            c.put(x + gx * size + dx, y + gy * size + dy, col)
        x += (len(g[0]) + 1) * size if g else 4 * size
    return x


def draw_scaled(c, rows, pal, cx, by, scale):
    """Draw a sprite scaled by `scale`, centred on cx, its bottom row at by."""
    h, w = len(rows), len(rows[0])
    sw, sh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    x0, y0 = int(round(cx - sw / 2)), by - sh + 1
    for yy in range(sh):
        row = rows[min(h - 1, int(yy / scale))]
        for xx in range(sw):
            col = pal.get(row[min(w - 1, int(xx / scale))])
            if col is not None:
                c.put(x0 + xx, y0 + yy, col)


def kart_pal(k):
    _, body, helmet, ears = DRIVERS[k]
    return {"b": body, "B": mix(body, (0, 0, 0), 0.45), "h": helmet, "e": ears, "w": (25, 25, 30),
            "x": (120, 120, 130), "t": (255, 40, 40), "v": (40, 40, 60)}


def render_kart(cfg, width=64, height=64, t=0.0, night=False):
    cfg = cfg or {}
    seed = cfg.get("seed", 0)
    if night:
        t = COUNTDOWN + 9.0
    race, tr = divmod(t, RACE_T)
    race = int(race)
    c = circuit(seed, race)
    pts, length = c["pts"], c["length"]
    canvas = Canvas(width, height)
    s, leads = progress(seed, race, tr, length)
    tick = int(t * 10)

    # Camera: behind the player, looking along the track a little ahead.
    z_player = CAM_H * FOCAL / (57 - HZ)
    lat_p = lateral(seed, race, 0, s, c)
    px, py, nx, ny = frame_at(pts, length, s)
    px, py = px + nx * lat_p, py + ny * lat_p
    ang = heading(pts, length, s + 4)
    fx, fy = math.cos(ang), math.sin(ang)
    rx, ry = -fy, fx
    cx, cy = px - fx * z_player, py - fy * z_player

    # Sky, far mountains and near hills: they slide sideways as the heading turns.
    shift = ang * 40
    for y in range(HZ):
        col = mix(SKY[0], SKY[1], y / float(HZ))
        for x in range(width):
            canvas.px[y * width + x] = col
    for i in range(4):
        cxp = int((rand(seed, race, "cl", i) * 160 - shift * 0.6) % 160) - 40
        cyp = 4 + int(rand(seed, race, "cly", i) * 8)
        for dx in range(-6, 7):
            for dy in range(-1 - (abs(dx) < 4), 1):
                canvas.put(cxp + dx, cyp + dy, (245, 248, 255))
    for x in range(width):
        wx = x + shift
        m = HZ - 4 - 4 * (0.5 + 0.5 * math.sin(wx * 0.045)) - 2 * math.sin(wx * 0.11)
        h = HZ - 1 - 2.5 * (0.5 + 0.5 * math.sin(wx * 0.09 + 1)) - 1.5 * (0.5 + 0.5 * math.sin(wx * 0.23))
        for y in range(int(m), HZ):
            canvas.put(x, y, MOUNT if y < h else HILLS[int(wx // 6) % 2])

    # The floor plane.
    dist, near = c["dist"], c["near"]
    for y in range(HZ, height):
        z = CAM_H * FOCAL / (y - HZ + 0.6)
        haze = min(1.0, max(0.0, (z - 40) / 160.0))
        bx, by = cx + fx * z, cy + fy * z
        step = z / FOCAL
        for x in range(width):
            lx = (x - 31.5) * step
            wx, wy = bx + rx * lx, by + ry * lx
            gx, gy = int(wx), int(wy)
            if 0 <= gx < GRID and 0 <= gy < GRID:
                k = gy * GRID + gx
                d, i = dist[k], near[k]
            else:
                d, i = 99.0, 0
            if d < ROAD:
                if i < 3 or i >= NPTS - 1:               # start line, chequered
                    col = (250, 250, 250) if (int(wx * 0.5) + int(wy * 0.5)) % 2 else (20, 20, 20)
                else:
                    col = ASPHALT[(gx // 3 + gy // 3) % 2]
                    if d < 0.45 and (i // 6) % 2 == 0:
                        col = (220, 220, 200)
            elif d < ROAD + KERB:
                col = KERBS[(i // 3) % 2]
            else:
                col = GRASS[(int(wx) // 8 + int(wy) // 8) % 2]
            canvas.px[y * width + x] = mix(col, HAZE, haze)

    # Billboards: trees, crystals and rival karts, far to near.
    def project(wx, wy):
        dx, dy = wx - cx, wy - cy
        zf = dx * fx + dy * fy
        if zf < 3:
            return None
        lx = dx * rx + dy * ry
        return 31.5 + lx * FOCAL / zf, HZ + CAM_H * FOCAL / zf, zf

    things = []
    for tx, ty in c["trees"]:
        p = project(tx, ty)
        if p and p[2] < 200 and -10 < p[0] < 74:
            things.append((p[2], "tree", p, None))
    for cs, clat in c["crystals"]:
        rel = (cs - s) % length
        if 3 < rel < 160:
            x0, y0, nx0, ny0 = frame_at(pts, length, cs)
            p = project(x0 + nx0 * clat, y0 + ny0 * clat)
            if p:
                things.append((p[2], "crystal", p, None))
    for k, lead in enumerate(leads, start=1):
        if -8 < lead < 150:
            sk = s + lead
            lat = lateral(seed, race, k, sk, c)
            x0, y0, nx0, ny0 = frame_at(pts, length, sk)
            p = project(x0 + nx0 * lat, y0 + ny0 * lat)
            if p:
                things.append((p[2], "kart", p, k))
    for zf, kind, (sx, sy, _), k in sorted(things, key=lambda q: -q[0]):
        scale = 12.0 / zf
        if kind == "tree":
            sc = scale * 1.6
            trunk_h = max(1, int(3 * sc))
            for yy in range(trunk_h):
                for xx in range(max(1, int(sc))):
                    canvas.put(int(sx) + xx, int(sy) - yy, TREE[2])
            rr = max(1.0, 4 * sc)
            ccx, ccy = sx, sy - trunk_h - rr * 0.9
            for yy in range(int(-rr), int(rr) + 1):
                for xx in range(int(-rr), int(rr) + 1):
                    if xx * xx + yy * yy <= rr * rr:
                        canvas.put(int(ccx + xx), int(ccy + yy), TREE[1] if xx + yy < -rr * 0.4 else TREE[0])
        elif kind == "crystal":
            bob = math.sin(t * 4 + zf) * 1.5 * scale
            h = max(1, int(3 * scale))
            for yy in range(-h, h + 1):
                w = h - abs(yy)
                for xx in range(-w, w + 1):
                    canvas.put(int(sx) + xx, int(sy - 4 * scale - h + yy + bob),
                               CRYSTAL[1] if xx == -w + (w > 0) and yy < 0 else CRYSTAL[0])
        else:
            curv = curvature(pts, length, s + leads[k - 1])
            rows = KART_LEAN if abs(curv) > 0.006 else KART
            draw_scaled(canvas, rows, kart_pal(k), sx, int(sy), scale * 0.85)

    # The player's kart, leaning into the bends.
    curv = curvature(pts, length, s + 4)
    lean = -1 if curv < -0.006 else 1 if curv > 0.006 else 0
    rows = KART_LEAN if lean else KART
    if lean > 0:
        rows = [r[::-1] for r in rows]
    bob = 1 if (tick // 2) % 2 and tr > COUNTDOWN and not night else 0
    draw_scaled(canvas, rows, kart_pal(0), 32, 61 - bob, 1.0)
    # Collected crystals sparkle round the player's kart.
    for cs, clat in c["crystals"]:
        rel = (s - cs) % length
        if 0 < rel < 4 and abs(clat - lat_p) < 3 and tr > COUNTDOWN:
            for j in range(6):
                a = j * 1.05 + t * 8
                canvas.put(32 + int(math.cos(a) * 8), 55 + int(math.sin(a) * 4), CRYSTAL[1])

    # HUD: position and lap; countdown lights; chequered finish.
    pos = 1 + sum(1 for lead in leads if lead > 0)
    lap = min(LAPS, 1 + int(s // length))
    suffix = {1: "ST", 2: "ND", 3: "RD"}.get(pos, "TH")
    hud = (255, 230, 60)
    if tr < COUNTDOWN + DRIVE:
        x = text(canvas, str(pos), 1, 1, hud, 2, (0, 0, 0))
        text(canvas, suffix, x, 1, hud, 1, (0, 0, 0))
        text(canvas, "L%d/%d" % (lap, LAPS), 46, 1, (255, 255, 255), 1, (0, 0, 0))
    if tr < COUNTDOWN + 0.6:
        lit = int(tr / (COUNTDOWN / 3))
        for i in range(3):
            col = (255, 40, 30) if i < lit and lit < 3 else (40, 255, 60) if lit >= 3 else (60, 20, 20)
            for dx in range(3):
                for dy in range(3):
                    canvas.put(25 + i * 5 + dx, 12 + dy, col)
    elif tr > COUNTDOWN + DRIVE:
        for y in range(16, 34):
            for x in range(10, 54):
                canvas.put(x, y, (250, 250, 250) if ((x - int(tr * 8)) // 3 + y // 3) % 2 else (15, 15, 15))
        for y in range(19, 31):
            for x in range(16, 48):
                canvas.put(x, y, (20, 20, 60))
        x = text(canvas, str(pos), 20, 20, hud, 2)
        text(canvas, suffix, x + 1, 25, hud, 1)
    return canvas.px
