"""Live view of the matrices in a browser, served by AppDaemon's own web server (`web: true`).

  /app/matrix         the page
  /app/matrix_info    JSON: matrices (name, host, size, screen showing) and screen names
  /app/matrix_frame   raw RGB bytes, row by row (?mode=mirror&m=<index>, or ?mode=preview&screen=<name>&night=0|1)

Mirror shows the last frame actually sent to a matrix, so it runs at the matrix's own rate (about 1 frame a second
for still screens, `frame_rate` for animated ones). Preview draws any screen on demand from live states, as fast as
the page asks, which is handy when designing screens away from the panels. No login: AppDaemon's web server is
local; the page only reads.
"""


def frame_bytes(pixels):
    """Pixels [(r, g, b), ...] as bytes r g b r g b ..."""
    return bytes(v for p in pixels for v in p)


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
  .hidden { display: none !important; }
</style>
</head>
<body>
<header>
  <h1>Matrix live view</h1>
  <div class="seg" role="group" aria-label="Mode">
    <button id="mMirror" aria-pressed="true">Mirror</button>
    <button id="mPreview" aria-pressed="false">Preview</button>
  </div>
  <label id="lMatrix">Matrix <select id="matrix"></select></label>
  <label id="lScreen" class="hidden">Screen <select id="screen"></select></label>
  <label id="lFps" class="hidden">Speed <select id="fps"><option>5</option><option selected>10</option><option>20</option><option>30</option></select> fps</label>
  <label id="lNight" class="hidden"><input type="checkbox" id="night"> Night</label>
  <label>Look <select id="look"><option value="dots" selected>LED dots</option><option value="square">Squares</option></select></label>
</header>
<main>
  <canvas id="c" width="640" height="640" aria-label="Matrix picture"></canvas>
  <div id="status">Connecting…</div>
</main>
<script>
const $ = (id) => document.getElementById(id);
const base = location.pathname.replace(/\/matrix\/?$/, "");
let mode = "mirror", info = null, last = null, frames = 0, fpsShown = 0, tick = performance.now();

function setMode(m) {
  mode = m;
  $("mMirror").setAttribute("aria-pressed", m === "mirror");
  $("mPreview").setAttribute("aria-pressed", m === "preview");
  $("lMatrix").classList.toggle("hidden", m !== "mirror");
  for (const id of ["lScreen", "lFps", "lNight"]) $(id).classList.toggle("hidden", m !== "preview");
  save();
}
$("mMirror").onclick = () => setMode("mirror");
$("mPreview").onclick = () => setMode("preview");
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
}

function draw(bytes, w, h) {
  const c = $("c"), ctx = c.getContext("2d"), p = 10;
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

async function loadInfo() {
  info = await (await fetch(base + "/matrix_info", { cache: "no-store" })).json();
  const keepM = $("matrix").value, keepS = $("screen").value;
  $("matrix").innerHTML = info.matrices.map((m) => `<option value="${m.id}">${m.name}</option>`).join("");
  $("screen").innerHTML = info.screens.map((s) => `<option>${s}</option>`).join("");
  if (keepM) $("matrix").value = keepM;
  if (keepS) $("screen").value = keepS;
}

async function step() {
  const t0 = performance.now();
  let wait = 100;
  try {
    let url;
    if (mode === "mirror") url = `${base}/matrix_frame?mode=mirror&m=${$("matrix").value}`;
    else {
      url = `${base}/matrix_frame?mode=preview&screen=${encodeURIComponent($("screen").value)}&night=${$("night").checked ? 1 : 0}`;
      wait = 1000 / Number($("fps").value);
    }
    const r = await fetch(url, { cache: "no-store" });
    if (r.status === 204) { $("status").textContent = "Nothing sent to this matrix yet (off, or nothing to show)"; }
    else if (!r.ok) { $("status").textContent = `Error ${r.status}: ${await r.text()}`; wait = 2000; }
    else {
      const buf = new Uint8Array(await r.arrayBuffer());
      const w = Number(r.headers.get("X-Width")), h = Number(r.headers.get("X-Height"));
      draw(buf, w, h);
      frames++;
      const now = performance.now();
      if (now - tick >= 1000) { fpsShown = frames * 1000 / (now - tick); frames = 0; tick = now; }
      const age = r.headers.get("X-Age-Ms");
      $("status").textContent = mode === "mirror"
        ? `${info.matrices[$("matrix").value].name}: ${r.headers.get("X-Screen")} · frame sent ${age} ms ago`
        : `Preview: ${r.headers.get("X-Screen")}${$("night").checked ? " (night)" : ""} · ${fpsShown.toFixed(1)} fps`;
    }
  } catch (e) { $("status").textContent = "Can't reach AppDaemon: " + e; wait = 2000; }
  setTimeout(step, Math.max(0, wait - (performance.now() - t0)));
}

(async () => {
  try { await loadInfo(); } catch (e) { $("status").textContent = "Can't load matrix list: " + e; }
  restore();
  setInterval(() => loadInfo().catch(() => {}), 30000);
  step();
})();
</script>
</body>
</html>
"""
