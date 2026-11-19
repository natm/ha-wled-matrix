"""Live view of the matrices in a browser, served by AppDaemon's own web server (`web: true`).

  /app/matrix         the page
  /app/matrix_info    JSON: matrices (name, host, size, screen showing) and screen names
  /app/matrix_frame   raw RGB bytes, row by row (?mode=mirror&m=<index>, or ?mode=preview&screen=<name>&night=0|1)
  /app/matrix_pin     ?m=<index>&screen=<name>|Auto: show that screen on the matrix now (Auto: back to its rotation)
  /app/matrix_card    the dashboard card (a JavaScript module to add as a Home Assistant dashboard resource)
  /app/matrix_yaml    ?screen=<name>: a configured screen as YAML; ?type=<key>: starting YAML for a screen type
  /app/matrix_scratch ?yaml=<text>: build a screen from the editor's YAML, kept apart from the config -> {"id"};
                      ?reroll=<id>: draw its {random: ...} values again. Preview it with matrix_frame ...&scratch=<id>

The page has three views: Mirror (one matrix), Preview (any screen, drawn on demand, with an editor: its YAML can be
changed and run here, and screen types not in the config tried) and All (every matrix with what it shows and a picker
to pin a screen). `?view=all&embed=1` is the All view without the header, for a Webpage card.
Every response allows any origin (CORS), so the card can call these from a Home Assistant dashboard.

Mirror shows the last frame actually sent to a matrix, so it runs at the matrix's own rate (about 1 frame a second
for still screens, `frame_rate` for animated ones). Preview draws any screen on demand from live states, as fast as
the page asks, which is handy when designing screens away from the panels. No login: AppDaemon's web server is
local; the page only reads.
"""

import asyncio
import hashlib
import pathlib
import time

from .screens import Screen, build

SCRATCH_TTL = 600  # seconds a screen made in the editor is kept after its last frame
CARD = pathlib.Path(__file__).with_name("static") / "wled_matrix_card.js"
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Expose-Headers": "X-Screen, X-Width, X-Height, X-Age-Ms",
    "Cache-Control": "no-store",
}


TEMPLATES = {  # starting YAML in the editor for a screen type; any other type gets `<key>:` and a pointer to its docs
    "rows": "rows:\n  - icon: mdi:thermometer\n    entity: sensor.outside_temperature\n    format: decimal1\n    unit: C\n"
    "  - icon: mdi:power-plug\n    entity: sensor.house_load_power\n    format: power\n",
    "camera": "camera: camera.front_door   # a camera entity\nfit: crop                   # crop or letterbox\ndwell: 15\n",
}


def types():
    """The screen types the editor offers: `rows` (the default screen) and every registered key."""
    return ["rows", *sorted(Screen.registry)]


def template(key):
    """Starting YAML for the editor when a screen type is picked rather than a configured screen."""
    if key in TEMPLATES:
        return TEMPLATES[key]
    return f"{key}:\n  # options: see docs/screens/{key.replace('_', '-')}.md\nframe_rate: 5\ndwell: 15\n"


def parse_screen(text):
    """A screen config from the editor's YAML: one entry as written under `screens:` in apps.yaml."""
    import yaml  # AppDaemon depends on PyYAML; imported here so the rest of the module needs nothing extra

    try:
        screen = yaml.safe_load(text or "")
    except yaml.YAMLError as err:
        raise ValueError(f"not valid YAML: {err}") from None
    if not isinstance(screen, dict) or not screen:
        raise ValueError(
            "the screen must be a mapping, as one entry under `screens:` in apps.yaml (e.g. `aquarium: {}`)"
        )
    if mentions(screen, "coastline"):
        raise ValueError("`coastline` (a file on the server) can't be used from the editor")
    return screen


def mentions(value, key):
    """True if `key` appears as a mapping key anywhere in `value`."""
    if isinstance(value, dict):
        return key in value or any(mentions(v, key) for v in value.values())
    return isinstance(value, list) and any(mentions(v, key) for v in value)


def screen_yaml(screen):
    """A configured screen as YAML for the editor, in the order it was written, placeholders and all."""
    import yaml  # see parse_screen

    return yaml.safe_dump(screen, sort_keys=False, allow_unicode=True)


class Scratch:
    """Screens built from YAML typed into the live view, kept apart from the configured ones: never in a rotation,
    never started, dropped SCRATCH_TTL seconds after their last use. The same text gives the same id, so the page can
    keep asking for frames while the user reads them, and a rebuild happens only when the text changes."""

    def __init__(self, host, ttl=SCRATCH_TTL, clock=time.monotonic):
        self.host, self.ttl, self.clock = host, ttl, clock
        self.items = {}  # id -> [last used, Screen]

    def add(self, text):
        """Build (or reuse) the screen for `text`; returns its id. Raises ValueError for YAML or config problems."""
        screen = parse_screen(text)
        key = hashlib.sha1(text.encode()).hexdigest()[:12]
        if key not in self.items:
            self.items[key] = [self.clock(), build(self.host, "editor", screen)]
        self.items[key][0] = self.clock()
        self.expire()
        return key

    def get(self, key):
        item = self.items.get(key)
        if item is None:
            return None
        item[0] = self.clock()
        return item[1]

    def reroll(self, key):
        """Draw the screen's `{random: ...}` values again, as a new visit would."""
        screen = self.get(key)
        if screen is not None:
            screen.on_show()
        return screen

    def expire(self):
        now = self.clock()
        for key in [k for k, (used, _) in self.items.items() if now - used > self.ttl]:
            del self.items[key]


def headers(**extra):
    """Response headers: CORS for the dashboard card, no caching, plus `extra` (X-Screen and friends)."""
    return {**CORS, **{k.replace("_", "-"): str(v) for k, v in extra.items()}}


def frame_bytes(pixels):
    """Pixels [(r, g, b), ...] as bytes r g b r g b ..."""
    return bytes(v for p in pixels for v in p)


def info(matrices, mirror, screens, now, status=None):
    """The /app/matrix_info payload: each matrix with what it's showing and how old that frame is, plus whatever
    `status(m)` adds (pinned, next, remaining, dwell, its screens, enabled, select, sensor), and every screen name."""
    rows = []
    for i, m in enumerate(matrices):
        shown = mirror.get(m["host"])
        rows.append(
            {
                "id": i,
                "name": m.get("name", m["host"]),
                "host": m["host"],
                "width": m.get("width", 64),
                "height": m.get("height", 64),
                "showing": shown[1] if shown else None,
                "age": round(now - shown[0], 1) if shown else None,
                **(status(m) if status else {}),
            }
        )
    return {"matrices": rows, "screens": sorted(screens), "types": types()}


class LiveView:
    """The live view's routes on AppDaemon's web server. The app gives `register()` its `register_route`, and the
    routes read the app's `matrices`, `screens` and `mirror` (host -> (time sent, screen name, pixels)), draw
    previews with its `render(name, width, height, night)`, and pin screens with its `pin(host, name)`."""

    def __init__(self, app):
        self.app = app
        self.scratch = Scratch(app)

    def register(self):
        self.app.register_route(self.page, "matrix")
        self.app.register_route(self.info, "matrix_info")
        self.app.register_route(self.frame, "matrix_frame")
        self.app.register_route(self.pin, "matrix_pin")
        self.app.register_route(self.card, "matrix_card")
        self.app.register_route(self.yaml, "matrix_yaml")
        self.app.register_route(self.scratch_route, "matrix_scratch")
        self.app.log("Live view: /app/matrix on AppDaemon's web server")

    async def yaml(self, request, kwargs):
        """?screen=<name>: that configured screen as YAML; ?type=<key>: starting YAML for a screen type."""
        from aiohttp import web  # AppDaemon ships aiohttp; imported here so tests run without it

        q = request.query
        if q.get("screen") is not None:
            if q["screen"] not in self.app.screens:
                return web.Response(status=404, text="unknown screen", headers=headers())
            return web.Response(
                text=screen_yaml(self.app.screens[q["screen"]]), content_type="text/plain", headers=headers()
            )
        if q.get("type") not in types():
            return web.Response(status=404, text="unknown screen type", headers=headers())
        return web.Response(text=template(q["type"]), content_type="text/plain", headers=headers())

    async def scratch_route(self, request, kwargs):
        """?yaml=<text>: build a screen from the editor's YAML -> {"id"}; ?reroll=<id>: draw its random values again."""
        from aiohttp import web  # AppDaemon ships aiohttp; imported here so tests run without it

        q = request.query
        if q.get("reroll"):
            if self.scratch.reroll(q["reroll"]) is None:
                return web.Response(status=404, text="that screen has expired: press Run again", headers=headers())
            return web.json_response({"id": q["reroll"]}, headers=headers())
        try:
            key = self.scratch.add(q.get("yaml", ""))
        except ValueError as err:
            return web.Response(status=400, text=str(err), headers=headers())
        except Exception as err:  # a screen type rejecting its config
            return web.Response(status=400, text=f"can't build the screen: {err!r}", headers=headers())
        return web.json_response({"id": key}, headers=headers())

    async def page(self, request, kwargs):
        from aiohttp import web  # AppDaemon ships aiohttp; imported here so tests run without it

        return web.Response(text=PAGE, content_type="text/html", headers=headers())

    async def card(self, request, kwargs):
        from aiohttp import web  # AppDaemon ships aiohttp; imported here so tests run without it

        return web.Response(text=CARD.read_text(), content_type="application/javascript", headers=headers())

    async def info(self, request, kwargs):
        from aiohttp import web  # AppDaemon ships aiohttp; imported here so tests run without it

        status = getattr(self.app, "matrix_status", None)
        payload = info(self.app.matrices, self.app.mirror, self.app.screens, time.monotonic(), status)
        return web.json_response(payload, headers=headers())

    async def pin(self, request, kwargs):
        """?m=<index>&screen=<name>: show that screen on the matrix now; screen=Auto (or empty) resumes the rotation."""
        from aiohttp import web  # AppDaemon ships aiohttp; imported here so tests run without it

        q = request.query
        try:
            m = self.app.matrices[int(q.get("m", 0))]
        except (ValueError, IndexError):
            return web.Response(status=404, text="unknown matrix", headers=headers())
        name = q.get("screen") or None
        try:
            self.app.pin(m["host"], None if name in (None, "Auto") else name)
        except ValueError as err:
            return web.Response(status=400, text=str(err), headers=headers())
        return web.json_response({"host": m["host"], "pinned": self.app.pinned.get(m["host"])}, headers=headers())

    async def frame(self, request, kwargs):
        """Raw RGB bytes, row by row. ?mode=mirror&m=<index>: the last frame sent to that matrix.
        ?mode=preview&screen=<name>&night=0|1&w=64&h=64: that screen drawn now from live states."""
        from aiohttp import web  # AppDaemon ships aiohttp; imported here so tests run without it

        q = request.query
        if q.get("mode") == "preview":
            w, h = int(q.get("w", 64)), int(q.get("h", 64))
            night = q.get("night") == "1"
            loop = asyncio.get_running_loop()
            if q.get("scratch"):  # a screen from the editor
                screen = self.scratch.get(q["scratch"])
                if screen is None:
                    return web.Response(status=404, text="that screen has expired: press Run again", headers=headers())
                name = "editor"
                try:
                    pixels = await loop.run_in_executor(None, self.app.render_pixels, screen, w, h, night)
                except Exception as err:  # the editor's config is the user's draft: show the error, don't log a trace
                    return web.Response(status=400, text=f"can't draw it: {err!r}", headers=headers())
            else:
                name = q.get("screen")
                if name not in self.app.screens:
                    return web.Response(status=404, text="unknown screen", headers=headers())
                pixels = await loop.run_in_executor(None, self.app.render, name, w, h, night)
            if pixels is None:
                pixels = [(0, 0, 0)] * (w * h)
            return web.Response(
                body=frame_bytes(pixels),
                content_type="application/octet-stream",
                headers=headers(X_Screen=name, X_Width=w, X_Height=h),
            )
        try:
            m = self.app.matrices[int(q.get("m", 0))]
        except (ValueError, IndexError):
            return web.Response(status=404, text="unknown matrix", headers=headers())
        w, h = m.get("width", 64), m.get("height", 64)
        shown = self.app.mirror.get(m["host"])
        if not shown:
            return web.Response(status=204, headers=headers())
        sent, name, pixels = shown
        return web.Response(
            body=frame_bytes(pixels),
            content_type="application/octet-stream",
            headers=headers(X_Screen=name, X_Width=w, X_Height=h, X_Age_Ms=int((time.monotonic() - sent) * 1000)),
        )


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Matrix live view</title>
<style>
  :root { color-scheme: dark; --bg: #0d0d0f; --panel: #17171b; --line: #2a2a30; --text: #e6e6e6; --dim: #9a9aa2; --accent: #03a9f4; }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 14px/1.4 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
  header { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; padding: 12px 16px; background: var(--panel); border-bottom: 1px solid var(--line); }
  h1 { font-size: 16px; font-weight: 600; margin: 0 8px 0 0; }
  label { color: var(--dim); display: inline-flex; gap: 6px; align-items: center; }
  select, button { background: #222228; color: var(--text); border: 1px solid var(--line); border-radius: 8px; padding: 6px 10px; font: inherit; min-height: 36px; }
  .seg { display: inline-flex; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
  .seg button { border: 0; border-radius: 0; background: transparent; }
  .seg button[aria-pressed="true"] { background: var(--accent); color: #fff; }
  main { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 16px; }
  canvas { background: #000; border-radius: 10px; max-width: 100%; height: auto; image-rendering: pixelated; }
  #status { color: var(--dim); font-variant-numeric: tabular-nums; text-align: center; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; width: 100%; max-width: 1100px; }
  .tile { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 10px; display: flex; flex-direction: column; gap: 8px; }
  .tile.pinned { border-color: var(--accent); }
  .tile canvas { width: 100%; border-radius: 6px; }
  .tile .row { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; }
  .tile .row .name { font-weight: 600; }
  .tile .row .state { color: var(--dim); text-align: right; }
  .tile.pinned .row .state { color: var(--accent); }
  .tile select { width: 100%; min-height: 32px; padding: 4px 8px; }
  .editor { width: 100%; max-width: 640px; display: flex; flex-direction: column; gap: 8px; }
  .ebar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .ebar .grow { flex: 1; color: var(--dim); font-size: 13px; }
  textarea { width: 100%; min-height: 160px; resize: vertical; font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background: #111114; color: var(--text); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
  #estatus { font-size: 13px; color: var(--dim); min-height: 18px; }
  #estatus.err { color: #ff7a7a; }
  .embed header { display: none; }
  .embed main { padding: 8px; }
  .hidden { display: none !important; }
</style>
</head>
<body>
<header>
  <h1>Matrix live view</h1>
  <div class="seg" role="group" aria-label="View">
    <button id="mMirror" aria-pressed="true">Mirror</button>
    <button id="mPreview" aria-pressed="false">Preview</button>
    <button id="mAll" aria-pressed="false">All</button>
  </div>
  <label id="lMatrix">Matrix <select id="matrix"></select></label>
  <label id="lScreen" class="hidden">Screen <select id="screen"></select></label>
  <label id="lFps" class="hidden">Speed <select id="fps"><option>5</option><option selected>10</option><option>20</option><option>30</option></select> fps</label>
  <label id="lNight" class="hidden"><input type="checkbox" id="night"> Night</label>
  <label>Look <select id="look"><option value="dots" selected>LED dots</option><option value="square">Squares</option></select></label>
</header>
<main>
  <canvas id="c" width="640" height="640" aria-label="Matrix picture"></canvas>
  <div id="all" class="tiles hidden"></div>
  <div id="status">Connecting…</div>
  <section id="editor" class="editor hidden" aria-label="Screen editor">
    <div class="ebar">
      <span class="grow" id="etitle">YAML</span>
      <button id="run" type="button" title="Draw this YAML here; the panel is unchanged">Run</button>
      <button id="reroll" type="button" title="Draw the {random: ...} values again">Reroll</button>
      <button id="reset" type="button" title="Back to the YAML as loaded">Reset</button>
    </div>
    <textarea id="yaml" spellcheck="false" aria-label="Screen YAML"></textarea>
    <div id="estatus"></div>
  </section>
</main>
<script>
const $ = (id) => document.getElementById(id);
const base = location.pathname.replace(/\/matrix\/?$/, "");
const params = new URLSearchParams(location.search);
let mode = "mirror", info = null, frames = 0, fpsShown = 0, tick = performance.now();
let scratchId = null, loadedFor = null, dirty = false;  // the editor: a screen built from its YAML, apart from the config
if (params.get("embed") === "1") document.body.classList.add("embed");
const isType = (v) => v.startsWith("type:");

function setMode(m) {
  mode = m;
  for (const [id, name] of [["mMirror", "mirror"], ["mPreview", "preview"], ["mAll", "all"]]) $(id).setAttribute("aria-pressed", m === name);
  $("lMatrix").classList.toggle("hidden", m !== "mirror");
  for (const id of ["lScreen", "lFps", "lNight"]) $(id).classList.toggle("hidden", m !== "preview");
  $("c").classList.toggle("hidden", m === "all");
  $("all").classList.toggle("hidden", m !== "all");
  $("editor").classList.toggle("hidden", m !== "preview");
  save();
  if (m === "preview" && info && loadedFor !== $("screen").value) loadYaml();
}
$("mMirror").onclick = () => setMode("mirror");
$("mPreview").onclick = () => setMode("preview");
$("mAll").onclick = () => setMode("all");
for (const id of ["matrix", "fps", "night", "look"]) $(id).onchange = save;
$("screen").onchange = () => { save(); loadYaml(); };

function estatus(text, err) { $("estatus").textContent = text; $("estatus").classList.toggle("err", !!err); }

async function loadYaml() {
  const v = $("screen").value;
  if (!v) return;
  const url = isType(v) ? `${base}/matrix_yaml?type=${encodeURIComponent(v.slice(5))}` : `${base}/matrix_yaml?screen=${encodeURIComponent(v)}`;
  try {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) { estatus(`Can't load YAML: ${await r.text()}`, true); return; }
    $("yaml").value = await r.text();
    loadedFor = v; scratchId = null; dirty = false;
    if (isType(v)) { $("etitle").textContent = `Screen type ${v.slice(5)}: not in your config`; await run(); }
    else { $("etitle").textContent = `${v}: as configured`; estatus("Live from your config. Edit and press Run to try changes here; the panel is unchanged."); }
  } catch (e) { estatus("Can't reach AppDaemon: " + e, true); }
}

async function run() {
  try {
    const r = await fetch(`${base}/matrix_scratch?yaml=${encodeURIComponent($("yaml").value)}`, { cache: "no-store" });
    if (!r.ok) { estatus(await r.text(), true); return; }
    scratchId = (await r.json()).id; dirty = false;
    estatus("Running your YAML here; the panel is unchanged. Copy it into apps.yaml under screens: to keep it.");
  } catch (e) { estatus("Can't reach AppDaemon: " + e, true); }
}

async function reroll() {
  if (!scratchId) { estatus("Press Run first.", true); return; }
  const r = await fetch(`${base}/matrix_scratch?reroll=${scratchId}`, { cache: "no-store" });
  if (!r.ok) { scratchId = null; await run(); }
}

$("run").onclick = run;
$("reroll").onclick = reroll;
$("reset").onclick = loadYaml;
$("yaml").oninput = () => { dirty = true; estatus("Edited: press Run to draw it."); };

function save() {
  try { localStorage.setItem("matrixView", JSON.stringify({ mode, matrix: $("matrix").value, screen: $("screen").value,
        fps: $("fps").value, night: $("night").checked, look: $("look").value })); } catch (e) {}
}
function restore() {
  try {
    const s = JSON.parse(localStorage.getItem("matrixView") || "{}");
    if (s.matrix) $("matrix").value = s.matrix;
    if (s.screen) $("screen").value = s.screen;
    if (s.fps) $("fps").value = s.fps;
    if (s.look) $("look").value = s.look;
    $("night").checked = !!s.night;
    if (s.mode) setMode(s.mode);
  } catch (e) {}
  if (params.get("view")) setMode(params.get("view"));
}

function draw(c, bytes, w, h, p) {
  const ctx = c.getContext("2d");
  if (c.width !== w * p || c.height !== h * p) { c.width = w * p; c.height = h * p; }
  ctx.fillStyle = "#000"; ctx.fillRect(0, 0, c.width, c.height);
  const dots = $("look").value === "dots";
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 3, r = bytes[i], g = bytes[i + 1], b = bytes[i + 2];
    const off = r + g + b === 0;
    ctx.fillStyle = off ? "#141416" : `rgb(${r},${g},${b})`;
    if (dots) { ctx.beginPath(); ctx.arc(x * p + p / 2, y * p + p / 2, p * 0.42, 0, 6.2832); ctx.fill(); }
    else ctx.fillRect(x * p, y * p, p - 1, p - 1);
  }
}

function tileStatus(m) {
  if (!m.enabled) return "off";
  if (!m.showing) return "nothing to show";
  if (m.pinned) return `${m.showing} · pinned`;
  return m.next ? `${m.showing} · ${m.next} in ${Math.round(m.remaining)} s` : m.showing;
}

async function pin(i, screen) {
  const r = await fetch(`${base}/matrix_pin?m=${i}&screen=${encodeURIComponent(screen)}`, { cache: "no-store" });
  if (!r.ok) $("status").textContent = `Can't pin: ${await r.text()}`;
  await loadInfo();
}

function buildTiles() {
  const all = $("all");
  all.innerHTML = "";
  for (const m of info.matrices) {
    const t = document.createElement("div");
    t.className = "tile"; t.id = `tile${m.id}`;
    t.innerHTML = `<canvas width="256" height="256" aria-label="${m.name}"></canvas>
      <div class="row"><span class="name"></span><span class="state"></span></div>
      <select aria-label="${m.name}: screen to show now"></select>`;
    const sel = t.querySelector("select");
    sel.onchange = () => pin(m.id, sel.value);
    all.appendChild(t);
  }
}

function updateTiles() {
  for (const m of info.matrices) {
    const t = $(`tile${m.id}`);
    if (!t) continue;
    t.classList.toggle("pinned", !!m.pinned);
    t.querySelector(".name").textContent = m.name;
    t.querySelector(".state").textContent = tileStatus(m);
    const sel = t.querySelector("select");
    const options = ["Auto", ...info.screens];
    if (sel.options.length !== options.length) sel.innerHTML = options.map((s) => `<option>${s}</option>`).join("");
    sel.value = m.pinned || "Auto";
    sel.disabled = !m.enabled;
  }
}

async function loadInfo() {
  const fresh = await (await fetch(base + "/matrix_info", { cache: "no-store" })).json();
  const rebuild = !info || info.matrices.length !== fresh.matrices.length;
  info = fresh;
  const keepM = $("matrix").value, keepS = $("screen").value;
  $("matrix").innerHTML = info.matrices.map((m) => `<option value="${m.id}">${m.name}</option>`).join("");
  $("screen").innerHTML = `<optgroup label="Configured">${info.screens.map((s) => `<option>${s}</option>`).join("")}</optgroup>`
    + `<optgroup label="Screen types (not in your config)">${(info.types || []).map((t) => `<option value="type:${t}">${t}</option>`).join("")}</optgroup>`;
  if (keepM) $("matrix").value = keepM;
  if (keepS) $("screen").value = keepS;
  if (!$("screen").value && info.screens.length) $("screen").value = info.screens[0];
  if (rebuild) buildTiles();
  updateTiles();
}

async function fetchFrame(url, canvas, p) {
  const r = await fetch(url, { cache: "no-store" });
  if (r.status === 204 || !r.ok) return r;
  const buf = new Uint8Array(await r.arrayBuffer());
  draw(canvas, buf, Number(r.headers.get("X-Width")), Number(r.headers.get("X-Height")), p);
  return r;
}

async function step() {
  const t0 = performance.now();
  let wait = 100;
  try {
    if (mode === "all") {
      wait = 1000;
      for (const m of info.matrices) {
        const t = $(`tile${m.id}`);
        if (t) await fetchFrame(`${base}/matrix_frame?mode=mirror&m=${m.id}`, t.querySelector("canvas"), 4);
      }
      $("status").textContent = `${info.matrices.length} matrix(es) · frames as sent, about once a second`;
    } else {
      let url;
      if (mode === "mirror") url = `${base}/matrix_frame?mode=mirror&m=${$("matrix").value}`;
      else {
        wait = 1000 / Number($("fps").value);
        const night = $("night").checked ? 1 : 0;
        if (scratchId) url = `${base}/matrix_frame?mode=preview&scratch=${scratchId}&night=${night}`;
        else if (isType($("screen").value)) { $("status").textContent = "Press Run to draw the YAML below"; setTimeout(step, 500); return; }
        else url = `${base}/matrix_frame?mode=preview&screen=${encodeURIComponent($("screen").value)}&night=${night}`;
      }
      const r = await fetchFrame(url, $("c"), 10);
      if (r.status === 204) { $("status").textContent = "Nothing sent to this matrix yet (off, or nothing to show)"; }
      else if (r.status === 404 && scratchId) { scratchId = null; await run(); }
      else if (!r.ok) { $("status").textContent = `Error ${r.status}: ${await r.text()}`; wait = 2000; }
      else {
        frames++;
        const now = performance.now();
        if (now - tick >= 1000) { fpsShown = frames * 1000 / (now - tick); frames = 0; tick = now; }
        const age = r.headers.get("X-Age-Ms");
        const shown = scratchId ? `your YAML${dirty ? " (edited, not run)" : ""}` : r.headers.get("X-Screen");
        $("status").textContent = mode === "mirror"
          ? `${info.matrices[$("matrix").value].name}: ${r.headers.get("X-Screen")} · frame sent ${age} ms ago`
          : `Preview: ${shown}${$("night").checked ? " (night)" : ""} · ${fpsShown.toFixed(1)} fps`;
      }
    }
  } catch (e) { $("status").textContent = "Can't reach AppDaemon: " + e; wait = 2000; }
  setTimeout(step, Math.max(0, wait - (performance.now() - t0)));
}

(async () => {
  try { await loadInfo(); } catch (e) { $("status").textContent = "Can't load matrix list: " + e; }
  restore();
  if (mode === "preview") loadYaml();
  setInterval(() => loadInfo().catch(() => {}), 5000);
  step();
})();
</script>
</body>
</html>
"""
