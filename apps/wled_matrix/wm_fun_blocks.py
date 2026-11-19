"""Blocks screen: an auto-playing falling-block puzzle. No entities needed.

Shapes of four squares fall into a well 10 wide and 20 deep (3 px a square). A simple player turns and slides each
one to a good spot and drops it; full rows flash, vanish and the stack above falls. On the right are the next shape,
the rows cleared and the score. When the stack gets high the well greys over, empties and a new game starts.

Original look: own colours, shapes named bar, box, tee, ess, zed, jay, ell. Pure Python, no dependencies.

Everything is a function of the time `t` (seconds): time is cut into `SLOT`-second slots, and the games in a slot
are simulated from (`seed`, slot number) and cached as a timeline, built only as far as the frame being asked for,
so drawing frames in order costs one shape's thinking about once a second. At night one still frame is drawn.

cfg keys: `seed` (default 0): a different run of games.
"""

from bisect import bisect_right

from wm_render import Canvas

COLS, ROWS, CELL = 10, 20, 3
WELL_X, WELL_Y = 2, 2                                 # top-left pixel of the well's inside
PANEL_X = 36
SLOT = 300.0          # seconds; every slot starts with a fresh game
STEP = 0.1            # seconds per row while the shape is being turned and slid into place
DROP = 0.045          # seconds per row once it's lined up
LOCK = 0.12           # pause after landing
FLASH = 0.55          # full rows flash and dissolve
COLLAPSE = 0.2        # the stack above falls
OVER = 3.0            # the game-over curtain
HIGH = 14             # a stack this many rows high ends the game
NIGHT_T = 41.3

# The seven shapes: (name, colour, squares as (x, y)).
SHAPES = [
    ("bar", (255, 50, 150), ((0, 0), (1, 0), (2, 0), (3, 0))),
    ("box", (150, 255, 30), ((0, 0), (1, 0), (0, 1), (1, 1))),
    ("tee", (255, 150, 0), ((1, 0), (0, 1), (1, 1), (2, 1))),
    ("ess", (30, 170, 255), ((1, 0), (2, 0), (0, 1), (1, 1))),
    ("zed", (255, 235, 0), ((0, 0), (1, 0), (1, 1), (2, 1))),
    ("jay", (255, 60, 40), ((0, 0), (0, 1), (1, 1), (2, 1))),
    ("ell", (160, 90, 255), ((2, 0), (0, 1), (1, 1), (2, 1))),
]
POINTS = (0, 10, 30, 60, 100)
GREY = (120, 125, 150)
WELL_BG = ((4, 6, 16), (9, 12, 28))
BORDER = ((0, 225, 255), (175, 60, 255))
LABEL = (110, 150, 255)

FONT = {
    "0": ["111", "101", "101", "101", "111"], "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"], "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"], "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"], "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"], "9": ["111", "101", "111", "001", "111"],
    "N": ["110", "101", "101", "101", "101"], "E": ["111", "100", "110", "100", "111"],
    "X": ["101", "101", "010", "101", "101"], "T": ["111", "010", "010", "010", "010"],
    "L": ["100", "100", "100", "100", "111"], "I": ["111", "010", "010", "010", "111"],
    "S": ["011", "100", "010", "001", "110"], "C": ["011", "100", "100", "100", "011"],
    "O": ["010", "101", "101", "101", "010"], "R": ["110", "101", "110", "101", "101"],
    "W": ["101", "101", "101", "111", "101"],
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


def turns(cells):
    """Every distinct quarter-turn of a shape, each moved to sit at (0, 0)."""
    out, cur = [], tuple(sorted(cells))
    for _ in range(4):
        if cur not in out:
            out.append(cur)
        h = max(y for _, y in cur) + 1
        cur = [(h - 1 - y, x) for x, y in cur]
        mx, my = min(x for x, _ in cur), min(y for _, y in cur)
        cur = tuple(sorted((x - mx, y - my) for x, y in cur))
    return out


TURNS = [turns(cells) for _, _, cells in SHAPES]


def fits(board, cells, x, row):
    for cx, cy in cells:
        px, py = x + cx, row + cy
        if px < 0 or px >= COLS or py >= ROWS or (py >= 0 and board[py][px]):
            return False
    return True


def choose(board, kind, noise_key):
    """The player: try every turn and column, dropped straight down, and score the well that results
    (few holes, low, level, rows cleared), with a little randomness so it isn't perfect."""
    heights = [0] * COLS
    for x in range(COLS):
        for y in range(ROWS):
            if board[y][x]:
                heights[x] = ROWS - y
                break
    best, best_score = (0, 3), None
    for rot, cells in enumerate(TURNS[kind]):
        width = max(cx for cx, _ in cells) + 1
        bottom = {}
        for cx, cy in cells:
            bottom[cx] = max(bottom.get(cx, 0), cy)
        for x in range(COLS - width + 1):
            row = min(ROWS - heights[x + cx] - b - 1 for cx, b in bottom.items())
            if row < 0:
                continue
            hs = heights[:]
            for cx, cy in cells:
                hs[x + cx] = max(hs[x + cx], ROWS - (row + cy))
            holes = sum(ROWS - heights[x + cx] - (row + b) - 1 for cx, b in bottom.items())
            rows_hit = {row + cy for _, cy in cells}
            cleared = 0
            for y in rows_hit:
                filled = sum(1 for v in board[y] if v) + sum(1 for _, cy in cells if row + cy == y)
                if filled == COLS:
                    cleared += 1
            bumps = sum(abs(hs[i] - hs[i + 1]) for i in range(COLS - 1))
            score = (-0.5 * sum(hs) + 8.0 * cleared - 7.5 * holes - 1.8 * bumps
                     - 1.2 * max(hs) + AI_NOISE * rand(noise_key, rot, x))
            if best_score is None or score > best_score:
                best, best_score = (rot, x), score
    return best


AI_NOISE = 16.0   # how much randomness blurs the player's judgement: higher = worse play, shorter games


class Timeline:
    """The games played in one slot, as a list of records, built on demand.

    A shape record: start, kind, next kind, moves [(time, x, turn, row)], lock time, cleared rows, the board before
    it, rows and score before it, end. A game-over record has kind None and the board it ended on.
    """

    def __init__(self, seed, slot):
        self.seed, self.slot = seed, slot
        self.records, self.starts = [], []
        self.time, self.done = 0.4, False
        self.new_game(0)

    def new_game(self, game):
        self.game, self.count, self.lines, self.score, self.over = game, 0, 0, 0, False
        self.board = [[0] * COLS for _ in range(ROWS)]

    def kind(self, n):
        order = sorted(range(7), key=lambda i: rand(self.seed, "bag", self.slot, self.game, n // 7, i))
        return order[n % 7]

    def until(self, when):
        while not self.done and self.time <= when:
            self.advance()

    def add(self, rec):
        self.starts.append(rec["start"])
        self.records.append(rec)
        self.time = rec["end"]

    def advance(self):
        board = self.board
        if self.over or self.time >= SLOT - OVER - 1.5:
            last = self.time >= SLOT - OVER - 1.5
            self.add({"start": self.time, "kind": None, "board": board, "lines": self.lines, "score": self.score,
                      "end": SLOT if last else self.time + OVER})
            self.done = last
            self.new_game(self.game + 1)
            return
        kind, nxt = self.kind(self.count), self.kind(self.count + 1)
        want_rot, want_x = choose(board, kind, (self.seed, "ai", self.slot, self.game, self.count))
        shapes = TURNS[kind]
        rot, x, row, tm = 0, 3, 0, self.time
        moves = [(tm, x, rot, row)]
        if fits(board, shapes[0], x, row):
            while (rot, x) != (want_rot, want_x):     # turn and slide, a step at a time, as it falls
                tm += STEP
                moved = False
                if rot != want_rot:
                    r2 = (rot + 1) % len(shapes)
                    x2 = min(x, COLS - 1 - max(cx for cx, _ in shapes[r2]))
                    if fits(board, shapes[r2], x2, row):
                        rot, x, moved = r2, x2, True
                if x != want_x and rot == want_rot or (x != want_x and not moved):
                    x2 = x + (1 if want_x > x else -1)
                    if fits(board, shapes[rot], x2, row):
                        x, moved = x2, True
                if fits(board, shapes[rot], x, row + 1):
                    row, moved = row + 1, True
                moves.append((tm, x, rot, row))
                if not moved:
                    break
            tm += STEP
            while fits(board, shapes[rot], x, row + 1):  # lined up: drop
                row += 1
                moves.append((tm, x, rot, row))
                tm += DROP
        lock = tm
        new = [r[:] for r in board]
        for cx, cy in shapes[rot]:
            if row + cy >= 0:
                new[row + cy][x + cx] = kind + 1
        cleared = [y for y in range(ROWS) if all(new[y])]
        rec = {"start": self.time, "kind": kind, "next": nxt, "moves": moves, "lock": lock, "cleared": cleared,
               "board": board, "lines": self.lines, "score": self.score,
               "end": lock + LOCK + (FLASH + COLLAPSE if cleared else 0)}
        if cleared:
            new = [[0] * COLS for _ in cleared] + [r for y, r in enumerate(new) if y not in cleared]
        self.board = new
        self.lines += len(cleared)
        self.score += POINTS[len(cleared)]
        self.count += 1
        self.over = any(any(r) for r in new[:ROWS - HIGH])
        self.add(rec)


_timelines = {}


def timeline_for(seed, slot):
    key = (seed, slot)
    if key not in _timelines:
        if len(_timelines) > 2:
            _timelines.clear()
        _timelines[key] = Timeline(seed, slot)
    return _timelines[key]


# --- Drawing -----------------------------------------------------------------------------------------------------
def draw_cell(c, x, y, col, dy=0):
    """One 3x3 square: lit top-left corner, shaded bottom-right."""
    px, py = WELL_X + x * CELL, WELL_Y + y * CELL + dy
    hi, lo = mix(col, (255, 255, 255), 0.55), scale(col, 0.55)
    for j in range(CELL):
        for i in range(CELL):
            if py + j >= WELL_Y:
                c.put(px + i, py + j, hi if i + j == 0 else (lo if i + j >= 3 else col))


def draw_text(c, text, x, y, col, size=1):
    for ch in text:
        for gy, row in enumerate(FONT[ch]):
            for gx, bit in enumerate(row):
                if bit == "1":
                    for j in range(size):
                        for i in range(size):
                            c.put(x + gx * size + i, y + gy * size + j, col)
        x += 4 * size
    return x


def draw_frame(c, width, height, glow):
    """The well, its border and the panel's labels."""
    for y in range(ROWS * CELL):
        for x in range(COLS * CELL):
            c.put(WELL_X + x, WELL_Y + y, WELL_BG[(x // CELL) % 2])
    x0, x1, y0, y1 = WELL_X - 1, WELL_X + COLS * CELL, WELL_Y - 1, WELL_Y + ROWS * CELL
    for y in range(y0, y1 + 1):
        col = mix(mix(BORDER[0], BORDER[1], (y - y0) / float(y1 - y0)), (255, 255, 255), glow)
        c.put(x0, y, col)
        c.put(x1, y, col)
        c.put(x0 - 1, y, scale(col, 0.3))
        c.put(x1 + 1, y, scale(col, 0.3))
    for x in range(x0, x1 + 1):
        c.put(x, y1, mix(BORDER[1], (255, 255, 255), glow))
        c.put(x, y0, scale(BORDER[0], 0.35))
    draw_text(c, "NEXT", PANEL_X + 6, 2, LABEL)
    for x in range(PANEL_X + 3, PANEL_X + 24):
        c.put(x, 9, scale(BORDER[0], 0.5))
        c.put(x, 21, scale(BORDER[1], 0.5))
    for y in range(9, 22):
        col = scale(mix(BORDER[0], BORDER[1], (y - 9) / 12.0), 0.5)
        c.put(PANEL_X + 3, y, col)
        c.put(PANEL_X + 23, y, col)
    draw_text(c, "ROWS", PANEL_X + 6, 26, LABEL)
    draw_text(c, "SCORE", PANEL_X + 4, 48, LABEL)


def draw_panel(c, nxt, lines, score, pop):
    if nxt is not None:
        _, col, cells = SHAPES[nxt]
        w = (max(x for x, _ in cells) + 1) * CELL
        h = (max(y for _, y in cells) + 1) * CELL
        ox, oy = PANEL_X + 13 - w // 2, 15 - h // 2 + (1 if h == 3 else 0)
        for cx, cy in cells:
            hi, lo = mix(col, (255, 255, 255), 0.55), scale(col, 0.55)
            for j in range(CELL):
                for i in range(CELL):
                    c.put(ox + cx * CELL + i, oy + cy * CELL + j, hi if i + j == 0 else (lo if i + j >= 3 else col))
    text = "%d" % (lines % 1000)
    draw_text(c, text, PANEL_X + 14 - len(text) * 4, 33, (255, 235, 0) if pop else (255, 255, 255), size=2)
    text = "%d" % (score % 100000)
    draw_text(c, text, PANEL_X + 14 - len(text) * 2, 55, (255, 255, 255))


def render_blocks(cfg, width=64, height=64, t=0.0, night=False):
    """Pixels for a `blocks:` screen."""
    cfg = cfg or {}
    seed = cfg.get("seed", 0)
    c = Canvas(width, height)
    if night:
        t = NIGHT_T
    slot, into = divmod(t, SLOT)
    tl = timeline_for(seed, int(slot))
    tl.until(into)
    i = bisect_right(tl.starts, into) - 1
    if i < 0:                                         # the moment before the first shape
        draw_frame(c, width, height, 0.0)
        draw_panel(c, tl.kind(0) if not tl.records else tl.records[0]["kind"], 0, 0, False)
        return c.px
    rec = tl.records[i]
    board, lines, score = rec["board"], rec["lines"], rec["score"]

    if rec["kind"] is None:                           # game over: a grey curtain rises, then the well empties
        age = into - rec["start"]
        draw_frame(c, width, height, 0.0)
        up = int(min(1.0, age / 1.1) * ROWS)
        gone = int(max(0.0, min(1.0, (age - 1.5) / 0.9)) * ROWS)
        for y in range(gone, ROWS):
            for x in range(COLS):
                if y >= ROWS - up:
                    draw_cell(c, x, y, GREY if (x + y) % 2 else scale(GREY, 0.8))
                elif board[y][x]:
                    draw_cell(c, x, y, SHAPES[board[y][x] - 1][1])
        draw_panel(c, None, lines, score, False)
        return c.px

    kind, moves, lock, cleared = rec["kind"], rec["moves"], rec["lock"], rec["cleared"]
    col = SHAPES[kind][1]
    after = into - lock
    glow = 0.0
    if cleared and after >= 0:
        glow = max(0.0, 1.0 - after / FLASH) * 0.8
        if after >= LOCK:
            lines += len(cleared)
            score += POINTS[len(cleared)]
    draw_frame(c, width, height, glow)

    tm, x, rot, row = moves[0]
    for m in moves:
        if m[0] <= into:
            tm, x, rot, row = m
    piece = {(x + cx, row + cy) for cx, cy in TURNS[kind][rot]}

    flash = after - LOCK if cleared else -1.0         # >= 0 once the rows start flashing
    fall = max(0.0, min(1.0, (flash - FLASH) / COLLAPSE)) if flash >= FLASH else 0.0
    for y in range(ROWS):
        below = sum(1 for r in cleared if r > y)
        dy = int(round(below * CELL * fall))
        for bx in range(COLS):
            v = board[y][bx]
            mine = (bx, y) in piece
            if not v and not mine:
                continue
            cc = col if mine else SHAPES[v - 1][1]
            if flash >= 0 and y in cleared:
                if flash >= FLASH:
                    continue
                if abs(bx - 4.5) < (flash - FLASH * 0.45) / (FLASH * 0.55) * 5.5:   # dissolves from the middle
                    continue
                cc = (255, 255, 255) if int(flash / 0.14) % 2 == 0 else mix(cc, (255, 255, 255), 0.4)
            elif mine and 0 <= after < LOCK:
                cc = mix(cc, (255, 255, 255), 0.6)    # a blink as it lands
            draw_cell(c, bx, y, cc, dy)
    draw_panel(c, rec["next"], lines, score, cleared and 0 <= after - LOCK < 1.0)
    return c.px
