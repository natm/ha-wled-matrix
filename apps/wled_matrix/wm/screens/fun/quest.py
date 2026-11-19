"""Quest screen: a little auto-playing top-down action-adventure in the 16-bit console style. No entities needed.

Pip the lantern-mage (purple pointed hat, blue robe, a staff with a glowing tip) crosses an endless run of rooms,
one screen each, 8 x 7 tiles of 8 px: meadow glades (trees, bushes, rocks, ponds, a dirt path), sandy shores (palms,
shells, pools) and old vaults (brick walls, pillars, lava). In each room Pip zaps the wandering monsters with the
staff (crabs, bats, wisps, beetles; they leave a coin), picks up coins, gems and potions, sometimes needs the key to
open the barred way out, then walks out and the screen scrolls to the next room. The bar at the top shows Pip's five
energy crystals, the key when held and the coin count.

All art, names and the bar are original to this app. Pure Python, no dependencies.

Everything is a function of the time `t` (seconds): time is cut into `QUEST_SECS` quests; the rooms of a quest are
generated from (`seed`, quest number, room number) and Pip's whole route through each (found by search) is laid out
on a timeline, built only as far as the frame asked for and cached. At night one still frame is drawn.

cfg keys: `seed` (default 0): a different world.
"""

import math
from bisect import bisect_right

from ...utils.canvas import Canvas, scale
from ...utils.noise import rand
from ..base import Screen

TILE, COLS, ROWS = 8, 8, 7
TOP = 8  # the room is drawn below the bar
QUEST_SECS = 240.0
STEP = 0.3  # seconds to walk one tile
ZAP = 0.8  # seconds per staff zap (the bolt flies 0.35-0.55 s in)
PAN = 0.9  # seconds for the screen to scroll to the next room
SIDES = {"E": (1, 0), "W": (-1, 0), "N": (0, -1), "S": (0, 1)}
OPPOSITE = {"E": "W", "W": "E", "N": "S", "S": "N"}
INK = (20, 12, 35)

BIOMES = [
    {
        "name": "meadow",
        "floor": ((120, 215, 80), (95, 190, 65)),
        "path": ((225, 185, 110), (200, 155, 85)),
        "walls": ("tree",),
        "things": ("tree", "bush", "rock", "water", "bush"),
        "monsters": ("crab", "bat"),
        "water": ((30, 110, 255), (130, 200, 255)),
    },
    {
        "name": "shore",
        "floor": ((245, 220, 135), (228, 196, 110)),
        "path": ((255, 240, 185), (240, 220, 150)),
        "walls": ("palm", "rock"),
        "things": ("palm", "rock", "water", "water", "shell"),
        "monsters": ("crab", "beetle"),
        "water": ((0, 190, 225), (170, 245, 255)),
    },
    {
        "name": "vault",
        "floor": ((66, 68, 96), (52, 54, 78)),
        "path": None,
        "walls": ("brick",),
        "things": ("pillar", "lava", "lava", "crate"),
        "monsters": ("wisp", "beetle", "bat"),
        "water": ((255, 90, 0), (255, 220, 40)),
    },
]

TILES = {
    "tree": ["..gGGg..", ".gGGGGg.", "gGhhGGGd", "gGhGGGGd", "gGGGGGdd", ".dGGGdd.", "..dttd..", "...tt..."],
    "bush": ["........", "..gGg...", ".gGGGgr.", "gGrGGGGd", "gGGGGrGd", ".dGGGdd.", "..dddd..", "........"],
    "rock": ["........", "..aaaa..", ".aAAAAa.", "aAhhAAAd", "aAhAAAAd", "aAAAAAdd", ".dddddd.", "........"],
    "palm": ["GG.gg.GG", "gGGggGGg", "..GGGG..", ".Gg.tgG.", "g..tt..g", "...tt...", "..tt....", "..tt...."],
    "shell": ["........", "........", "..pPp...", ".pPpPp..", ".PpPpP..", "..ppp...", "........", "........"],
    "brick": ["BBBmBBBm", "BBBmBBBm", "mmmmmmmm", "BmBBBmBB", "BmBBBmBB", "mmmmmmmm", "BBBmBBBm", "mmmmmmmm"],
    "pillar": ["..aaaa..", ".aAAAAd.", ".aAhAAd.", "..AhAd..", "..AhAd..", ".aAhAAd.", ".aAAAAd.", "..dddd.."],
    "crate": ["........", ".tttttt.", ".tTTTTt.", ".tTttTt.", ".tTttTt.", ".tTTTTt.", ".tttttt.", "........"],
}
TILE_COLS = {
    "g": (20, 150, 60),
    "G": (15, 120, 50),
    "h": (90, 220, 90),
    "d": (8, 80, 45),
    "t": (120, 70, 30),
    "T": (190, 125, 55),
    "r": (255, 60, 90),
    "a": (150, 155, 175),
    "A": (120, 125, 150),
    "p": (255, 150, 190),
    "P": (255, 215, 225),
    "B": (125, 100, 165),
    "m": (58, 44, 92),
}
VAULT_COLS = dict(TILE_COLS, a=(170, 160, 200), A=(135, 125, 175), h=(215, 205, 240), d=(70, 60, 110))

# Pip, 7 x 8. p hat, y hat band, s skin, k eye, r robe, R robe shade, b boot.
PIP = {
    "S": [
        ["...p...", "..ppp..", ".yyyyy.", ".sksks.", "..rrr..", ".rrrrr.", ".rRrRr.", "..b.b.."],
        ["...p...", "..ppp..", ".yyyyy.", ".sksks.", "..rrr..", ".rrrrr.", ".rRrRr.", ".b...b."],
    ],
    "N": [
        ["...p...", "..ppp..", ".yyyyy.", ".ppppp.", "..rrr..", ".rrrrr.", ".rRrRr.", "..b.b.."],
        ["...p...", "..ppp..", ".yyyyy.", ".ppppp.", "..rrr..", ".rrrrr.", ".rRrRr.", ".b...b."],
    ],
    "E": [
        ["...p...", "..ppp..", ".yyyyy.", "..pssk.", "..rrr..", "..rrrr.", "..rRr..", "..b.b.."],
        ["...p...", "..ppp..", ".yyyyy.", "..pssk.", "..rrr..", "..rrrr.", "..rRr..", "...bb.."],
    ],
}
PIP_COLS = {
    "p": (175, 70, 255),
    "y": (255, 225, 40),
    "s": (255, 205, 160),
    "k": INK,
    "r": (40, 150, 255),
    "R": (25, 95, 200),
    "b": (120, 60, 30),
}

MONSTERS = {
    "crab": (
        [
            ["r.w.w.r", "r.k.k.r", ".rrrrr.", "rrrrrrr", ".r.r.r."],
            ["..w.w..", "r.k.k.r", "rrrrrrr", ".rrrrr.", "r..r..r"],
        ],
        {"r": (255, 50, 40), "w": (255, 255, 255), "k": INK},
    ),
    "bat": (
        [
            ["p.....p", "pp.p.pp", "ppppppp", ".pwpwp.", "..ppp.."],
            [".......", "..p.p..", "ppppppp", "ppwpwpp", "p.ppp.p"],
        ],
        {"p": (215, 60, 255), "w": (255, 240, 0)},
    ),
    "wisp": (
        [
            ["...c...", "..ccc..", ".cwcwc.", ".ccccc.", ".c.c.c."],
            ["..c....", "..ccc..", ".cwcwc.", ".ccccc.", "..c.c.."],
        ],
        {"c": (60, 255, 230), "w": (255, 255, 255)},
    ),
    "beetle": (
        [
            ["k.....k", ".ggggg.", "ggygygg", "ggggggg", ".k.k.k."],
            [".k...k.", ".ggggg.", "ggygygg", "ggggggg", "k..k..k"],
        ],
        {"g": (150, 255, 30), "y": (255, 40, 40), "k": INK},
    ),
}
PICKUPS = {
    "coin": (["..x..", ".xgx.", "xgwgx", ".xgx.", "..x.."], {"g": (255, 215, 0), "w": (255, 255, 200), "x": INK}),
    "gem": ([".xxx.", "xgwgx", "xgggx", ".xgx.", "..x.."], {"g": (0, 235, 255), "w": (255, 255, 255), "x": INK}),
    "potion": (["..w..", ".xgx.", "xgggx", "xgwgx", ".xxx."], {"g": (255, 50, 90), "w": (255, 255, 255), "x": INK}),
    "key": (["xggx.", "xgxgx", ".xgx.", ".xgx.", ".xggx"], {"g": (255, 235, 60), "x": INK}),
}
VALUE = {"coin": 1, "gem": 5}

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


def mix(a, b, f):
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


def noise(a, b, c=0):
    n = (a * 374761393 + b * 668265263 + c * 2246822519) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return (n ^ (n >> 16)) & 0xFF


def inside(tile):
    return 1 <= tile[0] <= COLS - 2 and 1 <= tile[1] <= ROWS - 2


def search(start, goals, blocked, doors):
    """The shortest way from `start` to the nearest of `goals`, as a list of tiles (breadth-first)."""
    if start in goals:
        return [start]
    came, queue = {start: None}, [start]
    for cur in queue:
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in came or nxt in blocked or not (inside(nxt) or nxt in doors):
                continue
            came[nxt] = cur
            if nxt in goals:
                path = [nxt]
                while came[path[-1]] is not None:
                    path.append(came[path[-1]])
                return path[::-1]
            queue.append(nxt)
    return None


class Room:
    """One screen: what's in it and, second by second, what Pip does in it.

    `segs`: (start, end, kind, from tile, to tile, monster). kind "walk", "zap" or "pan" (the walk into the next
    room while the screen scrolls). `hud`: (time, coins, energy, has key).
    """

    def __init__(self, seed, quest, number, entry_side, entry_at, coins, energy):
        self.number = number
        r = lambda *k: rand(seed, "room", quest, number, *k)  # noqa: E731
        self.biome = BIOMES[(quest + number // 3) % len(BIOMES)]
        self.entry = self.door(entry_side, entry_at)
        sides = [s for s in "ENSW" if s != entry_side and not (number == 0 and s == "W")]
        self.exit_side = sides[int(r("side") * len(sides))]
        self.exit_at = 1 + int(r("at") * ((ROWS if self.exit_side in "EW" else COLS) - 2))
        self.exit = self.door(self.exit_side, self.exit_at)
        doors = {self.entry, self.exit}
        first, last = self.inner(self.entry), self.inner(self.exit)
        free = [(x, y) for y in range(1, ROWS - 1) for x in range(1, COLS - 1) if (x, y) not in (first, last)]
        order = sorted(free, key=lambda tl: r("order", tl))

        # Obstacles, then monsters and things to pick up on what's left; drop obstacles until all can be reached.
        things = {}
        for tl in order[: 4 + int(r("things") * 4)]:
            things[tl] = self.biome["things"][int(r("thing", tl) * len(self.biome["things"]))]
        spots = order[len(things) :]
        self.locked = r("locked") < (0.5 if self.biome["name"] == "vault" else 0.25)
        n_mon = 1 + int(r("monsters") * 2.4)
        self.monsters = [
            {
                "tile": tl,
                "kind": self.biome["monsters"][int(r("mk", tl) * len(self.biome["monsters"]))],
                "hp": 1 + int(r("hp", tl) * 2),
                "fight": 1e9,
                "dead": 1e9,
                "hits": [],
            }
            for tl in spots[:n_mon]
        ]
        kinds = ["coin", "coin", "gem", "coin"][: 2 + int(r("loot") * 3)]
        if self.locked:
            kinds.append("key")
        if energy < 5 and r("potion") < 0.7:
            kinds.append("potion")
        self.pickups = [{"tile": tl, "kind": k, "at": 1e9, "from": 0.0} for tl, k in zip(spots[n_mon:], kinds)]
        wanted = {m["tile"] for m in self.monsters} | {p["tile"] for p in self.pickups} | {last}
        for tl in sorted(things, key=lambda tl: r("drop", tl)):
            if all(search(first, {w}, set(things), doors) for w in wanted):
                break
            del things[tl]
        self.things = things
        self.trail = set(search(first, {last}, set(things), doors) or ()) | doors

        # Pip's route: always the nearest thing next (a monster is reached by a tile to zap it from).
        self.segs, self.hud = [], [(0.0, coins, energy, False)]
        now, pos, key = 0.0, self.entry, False
        todo = [("m", m) for m in self.monsters] + [("p", p) for p in self.pickups]

        def walk(path):
            nonlocal now, pos
            for nxt in path[1:]:
                self.segs.append((now, now + STEP, "walk", pos, nxt, None))
                now, pos = now + STEP, nxt

        walk([self.entry, first])
        while todo:
            alive = {m["tile"] for kind, m in todo if kind == "m"}
            blocked = set(things) | alive
            best = None
            for item in todo:
                kind, obj = item
                goals = self.zap_tiles(obj["tile"], blocked) if kind == "m" else {obj["tile"]}
                path = search(pos, goals, blocked, doors) if goals else None
                if path and (best is None or len(path) < len(best[1])):
                    best = (item, path)
            if best is None:
                break
            (kind, obj), path = best
            todo.remove(best[0])
            walk(path)
            if kind == "p":
                obj["at"] = now
                if obj["kind"] == "key":
                    key = True
                elif obj["kind"] == "potion":
                    energy = min(5, energy + 1)
                else:
                    coins += VALUE[obj["kind"]]
                self.hud.append((now, coins, energy, key))
            else:
                obj["fight"] = now
                if energy > 2 and r("hurt", obj["tile"]) < 0.3:  # it gets a nip in first
                    energy -= 1
                    self.hud.append((now + 0.25, coins, energy, key))
                for _ in range(obj["hp"]):
                    self.segs.append((now, now + ZAP, "zap", pos, obj["tile"], obj))
                    obj["hits"].append(now + 0.5)
                    now += ZAP
                obj["dead"] = obj["hits"][-1]
                drop = {"tile": obj["tile"], "kind": "coin", "at": 1e9, "from": obj["dead"] + 0.25}
                self.pickups.append(drop)
                todo.append(("p", drop))
        self.monsters = [m for m in self.monsters if m["fight"] < 1e9]
        self.pickups = [p for p in self.pickups if p["at"] < 1e9]
        self.unlocked = max([p["at"] for p in self.pickups if p["kind"] == "key"] or [0.0]) if self.locked else 0.0
        self.locked = self.locked and self.unlocked > 0
        walk(search(pos, {self.exit}, set(things), doors) or [pos, self.exit])
        dx, dy = SIDES[self.exit_side]
        self.segs.append((now, now + PAN, "pan", pos, (pos[0] + dx, pos[1] + dy), None))
        self.length = now + PAN
        if key:
            self.hud.append((now, coins, energy, False))
        self.coins, self.energy = coins, energy
        self.seg_starts = [s[0] for s in self.segs]
        self.hud_times = [h[0] for h in self.hud]

    @staticmethod
    def door(side, at):
        return {"E": (COLS - 1, at), "W": (0, at), "N": (at, 0), "S": (at, ROWS - 1)}[side]

    @staticmethod
    def inner(door):
        return (min(COLS - 2, max(1, door[0])), min(ROWS - 2, max(1, door[1])))

    def zap_tiles(self, target, blocked):
        """Tiles in line with `target`, 2-3 tiles off (or next to it), with nothing in between."""
        out = set()
        for dist in (2, 3, 1):
            for dx, dy in SIDES.values():
                tl = (target[0] + dx * dist, target[1] + dy * dist)
                between = [(target[0] + dx * k, target[1] + dy * k) for k in range(1, dist)]
                if inside(tl) and tl not in blocked and not any(b in blocked or not inside(b) for b in between):
                    out.add(tl)
            if out:
                return out
        return out


class Quest:
    def __init__(self, seed, number):
        self.seed, self.number = seed, number
        self.rooms, self.starts = [], []

    def until(self, when):
        """Build rooms until there's one that starts after `when` (so the next room is ready to scroll to)."""
        while not self.rooms or self.starts[-1] <= when:
            if self.rooms:
                last = self.rooms[-1]
                room = Room(
                    self.seed,
                    self.number,
                    len(self.rooms),
                    OPPOSITE[last.exit_side],
                    last.exit_at,
                    last.coins,
                    last.energy,
                )
                self.starts.append(self.starts[-1] + last.length)
            else:
                room = Room(self.seed, self.number, 0, "W", 3, 0, 5)
                self.starts.append(0.0)
            self.rooms.append(room)


_quests = {}


def quest_for(seed, number):
    key = (seed, number)
    if key not in _quests:
        if len(_quests) > 2:
            _quests.clear()
        _quests[key] = Quest(seed, number)
    return _quests[key]


# --- Drawing -----------------------------------------------------------------------------------------------------
def draw_sprite(c, rows, palette, x0, y0, flip=False, tint=None):
    w = len(rows[0])
    for gy, row in enumerate(rows):
        y = y0 + gy
        if y < TOP:
            continue
        for gx, ch in enumerate(row):
            col = palette.get(ch)
            if col is not None:
                c.put(x0 + (w - 1 - gx if flip else gx), y, tint or col)


def draw_room(c, room, now, ox, oy, t, width, height):
    """The room's tiles, pick-ups and monsters at room time `now`, shifted by (ox, oy) px."""
    biome = room.biome
    vault = biome["name"] == "vault"
    cols = VAULT_COLS if vault else TILE_COLS
    doors = (room.entry, room.exit)
    tick = int(t * 4)
    for ty in range(ROWS):
        for tx in range(COLS):
            x0, y0 = ox + tx * TILE, oy + ty * TILE
            if x0 <= -TILE or x0 >= width or y0 <= TOP - TILE or y0 >= height:
                continue
            tl = (tx, ty)
            wall = not inside(tl) and tl not in doors
            thing = room.things.get(tl)
            floor = biome["path"] if biome["path"] and tl in room.trail else biome["floor"]
            for j in range(TILE):
                y = y0 + j
                if y < TOP:
                    continue
                for i in range(TILE):
                    if vault:
                        col = floor[1] if i == 0 or j == 0 else floor[0]
                    else:
                        col = floor[1] if noise(room.number * 64 + tx * 8 + i, ty * 8 + j, 3) < 34 else floor[0]
                    c.put(x0 + i, y, col)
            if thing in ("water", "lava"):
                lo, hi = biome["water"]
                for j in range(TILE):
                    for i in range(TILE):
                        if y0 + j >= TOP:
                            c.put(
                                x0 + i,
                                y0 + j,
                                (
                                    hi
                                    if (i + tx * 8 + (j + ty * 8) * 3 + tick) % 9 == 0
                                    else (scale(lo, 0.8) if j == 0 and room.things.get((tx, ty - 1)) != thing else lo)
                                ),
                            )
            elif thing or wall:
                name = thing or biome["walls"][noise(tx, ty, room.number) % len(biome["walls"])]
                draw_sprite(c, TILES[name], cols, x0, y0)
    if room.locked and now < room.unlocked + 0.4:  # the barred way out, until the key is found
        x0, y0 = ox + room.exit[0] * TILE, oy + room.exit[1] * TILE
        for j in range(TILE):
            for i in range(TILE):
                if y0 + j >= TOP and (i % 2 == 0 or j in (1, 6)):
                    c.put(
                        x0 + i,
                        y0 + j,
                        (255, 255, 255) if now > room.unlocked else ((255, 200, 40) if j in (1, 6) else (190, 130, 30)),
                    )
    for p in room.pickups:
        if p["from"] <= now < p["at"]:
            rows, pal = PICKUPS[p["kind"]]
            x0, y0 = ox + p["tile"][0] * TILE + 2, oy + p["tile"][1] * TILE + 1
            if p["kind"] == "coin" and (tick + p["tile"][0]) % 4 == 3:
                rows = ["..x..", "..g..", "..w..", "..g..", "..x.."]
            draw_sprite(c, rows, pal, x0, y0 + (1 if (tick + p["tile"][1]) % 4 < 2 else 0))
        elif 0 <= now - p["at"] < 0.4:  # a sparkle as it's taken
            cx, cy = ox + p["tile"][0] * TILE + 4, oy + p["tile"][1] * TILE + 3
            d = 2 + int((now - p["at"]) * 10)
            for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
                if cy + dy >= TOP:
                    c.put(cx + dx, cy + dy, (255, 255, 255))
    for m in room.monsters:
        frames, pal = MONSTERS[m["kind"]]
        cx, cy = ox + m["tile"][0] * TILE, oy + m["tile"][1] * TILE + 1
        if now < m["dead"]:
            dt = min(0.0, now - m["fight"])  # it wanders, and is back on its tile when the fight starts
            wob = 3.0 * math.sin(dt * 2.1)
            dx, dy = (wob, 0) if m["kind"] in ("crab", "beetle") else (wob * 0.6, 2.0 * math.sin(dt * 3.3))
            hit = any(0 <= now - h < 0.15 for h in m["hits"])
            draw_sprite(
                c,
                frames[int(t * 4) % 2],
                pal,
                cx + int(round(dx)),
                cy + int(round(dy)),
                tint=(255, 255, 255) if hit else None,
            )
        elif now - m["dead"] < 0.3:  # a puff
            d = 1 + int((now - m["dead"]) * 14)
            for dx, dy in ((-d, -d), (d, -d), (-d, d), (d, d), (0, -d - 1), (0, d + 1), (-d - 1, 0), (d + 1, 0)):
                if cy + 2 + dy >= TOP:
                    c.put(cx + 3 + dx, cy + 2 + dy, (255, 255, 255) if d % 2 else pal[frames[0][2][3]])


def draw_hud(c, coins, energy, key, flash, width, tick):
    for y in range(TOP):
        for x in range(width):
            c.px[y * width + x] = (8, 8, 22) if y < TOP - 1 else (70, 60, 130)
    for i in range(5):  # energy crystals
        on = i < energy
        col = ((255, 80, 80) if flash else (60, 240, 255)) if on else (40, 50, 80)
        x = 1 + i * 4
        for dx, dy in ((1, 1), (0, 2), (1, 2), (2, 2), (0, 3), (1, 3), (2, 3), (1, 4), (1, 5)):
            c.put(x + dx, dy - 0, col)
        if on:
            c.put(x + 1, 2, (255, 255, 255))
    if key:
        draw_sprite_hud(c, PICKUPS["key"], 27, 1)
    draw_sprite_hud(c, PICKUPS["coin"], width - 19, 1)
    text = "%03d" % (coins % 1000)
    x = width - 12
    for ch in text:
        for gy, row in enumerate(DIGITS[ch]):
            for gx, bit in enumerate(row):
                if bit == "1":
                    c.put(x + gx, 1 + gy, (255, 255, 255))
        x += 4


def draw_sprite_hud(c, sprite, x0, y0):
    rows, pal = sprite
    for gy, row in enumerate(rows):
        for gx, ch in enumerate(row):
            if ch != "x" and ch in pal:
                c.put(x0 + gx, y0 + gy, pal[ch])


def still_time(seed):
    """A good moment for the night frame: Pip's first zap."""
    quest = quest_for(seed, 0)
    quest.until(60.0)
    for start, room in zip(quest.starts, quest.rooms):
        for seg in room.segs:
            if seg[2] == "zap":
                return start + seg[0] + 0.45
    return 3.0


def render_quest(cfg, width=64, height=64, t=0.0, night=False):
    """Pixels for a `quest:` screen."""
    cfg = cfg or {}
    seed = cfg.get("seed", 0)
    c = Canvas(width, height)
    if night:
        t = still_time(seed)
    number, into = divmod(t, QUEST_SECS)
    quest = quest_for(seed, int(number))
    quest.until(into)
    i = bisect_right(quest.starts, into) - 1
    room, now = quest.rooms[i], into - quest.starts[i]
    start, end, kind, a, b, target = room.segs[max(0, bisect_right(room.seg_starts, now) - 1)]
    f = max(0.0, min(1.0, (now - start) / (end - start)))

    # Where the screen is: still, or scrolling to the next room as Pip walks through the way out.
    ox = oy = 0
    if kind == "pan":
        dx, dy = SIDES[room.exit_side]
        slide = f * f * (3 - 2 * f)
        ox, oy = -int(round(dx * slide * COLS * TILE)), -int(round(dy * slide * ROWS * TILE))
        nxt = quest.rooms[i + 1]
        draw_room(c, nxt, 0.0, ox + dx * COLS * TILE, TOP + oy + dy * ROWS * TILE, t, width, height)
    draw_room(c, room, now, ox, TOP + oy, t, width, height)

    # Pip.
    facing = "S"
    px, py = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
    look = (b[0] - a[0], b[1] - a[1])
    if kind == "zap":
        px, py = a
    if abs(look[0]) >= abs(look[1]) and look[0]:
        facing = "E" if look[0] > 0 else "W"
    elif look[1]:
        facing = "S" if look[1] > 0 else "N"
    hx, hy = ox + int(round(px * TILE)), TOP + oy + int(round(py * TILE))
    j = bisect_right(room.hud_times, now) - 1
    _, coins, energy, key = room.hud[max(0, j)]
    hurt = j > 0 and room.hud[j][2] < room.hud[j - 1][2] and now - room.hud[j][0] < 0.35
    frame = int(now / (STEP / 2)) % 2 if kind != "zap" else 0
    rows = PIP["E" if facing == "W" else facing][frame]
    draw_sprite(c, rows, PIP_COLS, hx, hy, flip=facing == "W", tint=(255, 70, 70) if hurt else None)
    side = {"E": 1, "W": -1}.get(facing, 1 if facing == "S" else -1)
    sx, sy = hx + 3 + side * 4, hy + 2  # the staff: a pole with a glowing tip
    casting = kind == "zap" and 0.2 <= now - start < 0.6
    for k in range(1, 6):
        if sy + k >= TOP:
            c.put(sx, sy + k, (150, 90, 40))
    glow = (255, 255, 255) if casting else ((255, 235, 60) if int(t * 3) % 2 else (255, 170, 0))
    if sy >= TOP:
        c.put(sx, sy, glow)
        if casting:
            for dx, dy in ((1, 0), (-1, 0), (0, -1), (0, 1)):
                c.put(sx + dx, max(TOP, sy + dy), (255, 240, 120))
    if kind == "zap" and 0.33 <= now - start < 0.6:  # the bolt
        tx, ty = ox + b[0] * TILE + 3, TOP + oy + b[1] * TILE + 3
        n = max(abs(tx - sx), abs(ty - sy), 1)
        for k in range(n + 1):
            x, y = sx + (tx - sx) * k / float(n), sy + (ty - sy) * k / float(n)
            jig = (noise(k, int(now * 20)) % 3) - 1
            bx, by = (
                (int(round(x)), int(round(y)) + jig)
                if abs(tx - sx) > abs(ty - sy)
                else (int(round(x)) + jig, int(round(y)))
            )
            if by >= TOP:
                c.put(bx, by, (255, 255, 255) if k % 2 else (120, 230, 255))

    draw_hud(c, coins, energy, key, hurt, width, int(t * 4))
    k = 1.0 if night else min(1.0, into / 0.5, (QUEST_SECS - into) / 0.5)  # fade between quests
    if k < 1.0:
        c.px = [scale(p, k) for p in c.px]
    return c.px


class QuestScreen(Screen):
    key = "quest"

    def render(self, width, height, *, night, t, now):
        return render_quest(self.cfg, width, height, t=t, night=night)
