"""Live view of the matrices in a browser, served by AppDaemon's own web server (`web: true`).

  /app/matrix         the page
  /app/matrix_info    JSON: matrices (name, host, size, screen showing) and screen names
  /app/matrix_frame   raw RGB bytes, row by row (?mode=mirror&m=<index>, or ?mode=preview&screen=<name>&night=0|1)
  /app/matrix_pin     ?m=<index>&screen=<name>|Auto: show that screen on the matrix now (Auto: back to its rotation)
  /app/matrix_card    the dashboard card (a JavaScript module to add as a Home Assistant dashboard resource)

The page has three views: Mirror (one matrix), Preview (any screen, drawn on demand) and All (every matrix with what
it shows and a picker to pin a screen). `?view=all&embed=1` is the All view without the header, for a Webpage card.
Every response allows any origin (CORS), so the card can call these from a Home Assistant dashboard.

Mirror shows the last frame actually sent to a matrix, so it runs at the matrix's own rate (about 1 frame a second
for still screens, `frame_rate` for animated ones). Preview draws any screen on demand from live states, as fast as
the page asks, which is handy when designing screens away from the panels. No login: AppDaemon's web server is
local; the page only reads.
"""

import asyncio
import pathlib
import time

CARD = pathlib.Path(__file__).with_name("static") / "wled_matrix_card.js"
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Expose-Headers": "X-Screen, X-Width, X-Height, X-Age-Ms",
    "Cache-Control": "no-store",
}


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
    return {"matrices": rows, "screens": sorted(screens)}


class LiveView:
    """The live view's routes on AppDaemon's web server. The app gives `register()` its `register_route`, and the
    routes read the app's `matrices`, `screens` and `mirror` (host -> (time sent, screen name, pixels)), draw
    previews with its `render(name, width, height, night)`, and pin screens with its `pin(host, name)`."""

    def __init__(self, app):
        self.app = app

    def register(self):
        self.app.register_route(self.page, "matrix")
        self.app.register_route(self.info, "matrix_info")
        self.app.register_route(self.frame, "matrix_frame")
        self.app.register_route(self.pin, "matrix_pin")
        self.app.register_route(self.card, "matrix_card")
        self.app.log("Live view: /app/matrix on AppDaemon's web server")

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
            name = q.get("screen")
            if name not in self.app.screens:
                return web.Response(status=404, text="unknown screen", headers=headers())
            w, h = int(q.get("w", 64)), int(q.get("h", 64))
            night = q.get("night") == "1"
            loop = asyncio.get_running_loop()
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
</main>
<script>
const $ = (id) => document.getElementById(id);
const base = location.pathname.replace(/\/matrix\/?$/, "");
const params = new URLSearchParams(location.search);
let mode = "mirror", info = null, frames = 0, fpsShown = 0, tick = performance.now();
if (params.get("embed") === "1") document.body.classList.add("embed");

function setMode(m) {
  mode = m;
  for (const [id, name] of [["mMirror", "mirror"], ["mPreview", "preview"], ["mAll", "all"]]) $(id).setAttribute("aria-pressed", m === name);
  $("lMatrix").classList.toggle("hidden", m !== "mirror");
  for (const id of ["lScreen", "lFps", "lNight"]) $(id).classList.toggle("hidden", m !== "preview");
  $("c").classList.toggle("hidden", m === "all");
  $("all").classList.toggle("hidden", m !== "all");
  save();
}
$("mMirror").onclick = () => setMode("mirror");
$("mPreview").onclick = () => setMode("preview");
$("mAll").onclick = () => setMode("all");
for (const id of ["matrix", "screen", "fps", "night", "look"]) $(id).onchange = save;

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
  $("screen").innerHTML = info.screens.map((s) => `<option>${s}</option>`).join("");
  if (keepM) $("matrix").value = keepM;
  if (keepS) $("screen").value = keepS;
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
        url = `${base}/matrix_frame?mode=preview&screen=${encodeURIComponent($("screen").value)}&night=${$("night").checked ? 1 : 0}`;
        wait = 1000 / Number($("fps").value);
      }
      const r = await fetchFrame(url, $("c"), 10);
      if (r.status === 204) { $("status").textContent = "Nothing sent to this matrix yet (off, or nothing to show)"; }
      else if (!r.ok) { $("status").textContent = `Error ${r.status}: ${await r.text()}`; wait = 2000; }
      else {
        frames++;
        const now = performance.now();
        if (now - tick >= 1000) { fpsShown = frames * 1000 / (now - tick); frames = 0; tick = now; }
        const age = r.headers.get("X-Age-Ms");
        $("status").textContent = mode === "mirror"
          ? `${info.matrices[$("matrix").value].name}: ${r.headers.get("X-Screen")} · frame sent ${age} ms ago`
          : `Preview: ${r.headers.get("X-Screen")}${$("night").checked ? " (night)" : ""} · ${fpsShown.toFixed(1)} fps`;
      }
    }
  } catch (e) { $("status").textContent = "Can't reach AppDaemon: " + e; wait = 2000; }
  setTimeout(step, Math.max(0, wait - (performance.now() - t0)));
}

(async () => {
  try { await loadInfo(); } catch (e) { $("status").textContent = "Can't load matrix list: " + e; }
  restore();
  setInterval(() => loadInfo().catch(() => {}), 5000);
  step();
})();
</script>
</body>
</html>
"""
