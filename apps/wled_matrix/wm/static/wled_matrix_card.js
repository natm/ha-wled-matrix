/* WLED Matrix card for Home Assistant dashboards.

   Served by the app at http://<appdaemon>:5050/app/matrix_card (needs `web: true`). Add that URL as a dashboard
   resource (Settings > Dashboards > Resources, type "JavaScript module"), then:

     type: custom:wled-matrix-card
     url: http://<appdaemon>:5050/app   # where the live view is served
     matrix: Kitchen                    # a matrix's name, host or index
     picker: chips                      # chips (default): one per screen | dialog: tap the status line | none
     preview: true                      # the "Preview here" control (draws a screen in the card, not on the panel)
     fps: 2                             # how often the card fetches the frame being sent

   The card talks to AppDaemon directly, so the dashboard must be able to reach that URL (same network, or the
   AppDaemon add-on's ingress). A dashboard served over https can't load an http URL; see docs/dashboard.md. */

const AUTO = "Auto";

class WledMatrixCard extends HTMLElement {
  static getStubConfig() {
    return { url: "http://appdaemon.local:5050/app", matrix: 0 };
  }

  setConfig(config) {
    if (!config.url) throw new Error("wled-matrix-card: `url` is required (http://<appdaemon>:5050/app)");
    this._config = { picker: "chips", preview: true, fps: 2, ...config };
    this._base = String(config.url).replace(/\/+$/, "");
    this._mode = "live";
    this._previewScreen = null;
    this._render();
    if (this.isConnected) this._start();
  }

  set hass(hass) {
    this._hass = hass; // not needed: the card reads AppDaemon directly, so it works without any entity
  }

  getCardSize() {
    return 6;
  }

  connectedCallback() {
    if (this._config) this._start();
  }

  disconnectedCallback() {
    this._stop();
  }

  // ---------- data ----------
  _start() {
    this._stop();
    this._alive = true;
    this._poll();
    this._loop();
  }

  _stop() {
    this._alive = false;
    clearTimeout(this._infoTimer);
    clearTimeout(this._frameTimer);
  }

  async _poll() {
    if (!this._alive) return;
    try {
      const all = await (await fetch(`${this._base}/matrix_info`, { cache: "no-store" })).json();
      const want = this._config.matrix;
      this._m = all.matrices.find((m) => m.name === want || m.host === want || m.id === Number(want)) || all.matrices[0];
      this._screens = all.screens;
      this._error = this._m ? null : "no matrices";
    } catch (e) {
      this._error = `Can't reach ${this._base}`;
    }
    this._update();
    this._infoTimer = setTimeout(() => this._poll(), 2000);
  }

  async _loop() {
    if (!this._alive) return;
    let wait = 1000 / Number(this._config.fps || 2);
    if (this._m) {
      const url =
        this._mode === "preview" && this._previewScreen
          ? `${this._base}/matrix_frame?mode=preview&screen=${encodeURIComponent(this._previewScreen)}`
          : `${this._base}/matrix_frame?mode=mirror&m=${this._m.id}`;
      try {
        const r = await fetch(url, { cache: "no-store" });
        if (r.ok && r.status !== 204) {
          const bytes = new Uint8Array(await r.arrayBuffer());
          this._draw(bytes, Number(r.headers.get("X-Width")), Number(r.headers.get("X-Height")));
          this._blank = false;
        } else if (r.status === 204) {
          this._blank = true;
          this._draw(null, this._m.width, this._m.height);
        }
      } catch (e) {
        wait = 3000;
      }
    }
    this._frameTimer = setTimeout(() => this._loop(), wait);
  }

  async _pin(screen) {
    if (!this._m) return;
    try {
      const r = await fetch(`${this._base}/matrix_pin?m=${this._m.id}&screen=${encodeURIComponent(screen)}`, {
        cache: "no-store",
      });
      if (!r.ok) this._error = await r.text();
    } catch (e) {
      this._error = `Can't reach ${this._base}`;
    }
    clearTimeout(this._infoTimer);
    this._poll();
  }

  // ---------- drawing ----------
  _draw(bytes, w, h) {
    const c = this.shadowRoot.getElementById("c");
    if (!c || !w || !h) return;
    const p = 6;
    if (c.width !== w * p || c.height !== h * p) {
      c.width = w * p;
      c.height = h * p;
    }
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, c.width, c.height);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const i = (y * w + x) * 3;
        const lit = bytes && bytes[i] + bytes[i + 1] + bytes[i + 2] > 0;
        ctx.fillStyle = lit ? `rgb(${bytes[i]},${bytes[i + 1]},${bytes[i + 2]})` : "#141416";
        ctx.beginPath();
        ctx.arc(x * p + p / 2, y * p + p / 2, p * 0.42, 0, 6.2832);
        ctx.fill();
      }
    }
  }

  _statusText() {
    const m = this._m;
    if (this._error) return this._error;
    if (!m) return "Loading…";
    if (this._mode === "preview") return `Preview: ${this._previewScreen} (the panel is unchanged)`;
    if (!m.enabled) return "Off (its switch is off)";
    if (!m.showing) return "Nothing to show";
    if (m.pinned) return `Showing ${m.showing} · pinned`;
    return m.next ? `Showing ${m.showing} · ${m.next} in ${Math.round(m.remaining)} s` : `Showing ${m.showing}`;
  }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const cfg = this._config;
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
        .head { display: flex; align-items: center; justify-content: space-between; }
        .name { font-size: 20px; }
        .live { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--secondary-text-color); }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success-color, #4caf50); }
        .dot.off { background: var(--disabled-text-color, #666); }
        canvas { width: 100%; height: auto; display: block; border-radius: 8px; background: #000; image-rendering: pixelated; }
        .status { display: flex; justify-content: space-between; gap: 8px; font-size: 14px; }
        button.status { width: 100%; background: none; border: 0; padding: 0; font: inherit; color: var(--primary-text-color); cursor: pointer; text-align: left; }
        .bar { height: 4px; border-radius: 2px; background: var(--divider-color, #2c2c2c); overflow: hidden; }
        .bar div { height: 4px; background: var(--primary-color); transition: width 1s linear; }
        .label { font-size: 12px; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: 0.08em; }
        .chips { display: flex; flex-wrap: wrap; gap: 8px; }
        .chip { height: 36px; padding: 0 14px; border-radius: 18px; border: 1px solid var(--divider-color, #4a4a4a); background: transparent; color: var(--primary-text-color); font: inherit; font-size: 14px; cursor: pointer; }
        .chip.on { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
        .foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding-top: 8px; border-top: 1px solid var(--divider-color, #2a2a2a); }
        .foot label { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: var(--secondary-text-color); }
        select { height: 36px; padding: 0 8px; border-radius: 4px; border: 1px solid var(--divider-color, #4a4a4a); background: var(--card-background-color); color: var(--primary-text-color); font: inherit; }
        .err { color: var(--error-color, #db4437); }
        dialog { border: 0; border-radius: 28px; padding: 0; background: var(--card-background-color, #1c1c1c); color: var(--primary-text-color); width: min(400px, 90vw); box-shadow: 0 8px 24px rgba(0,0,0,0.6); }
        dialog::backdrop { background: rgba(0,0,0,0.55); }
        .dhead { display: flex; align-items: center; gap: 8px; padding: 16px 20px 0 12px; }
        .dhead h2 { margin: 0; font-size: 20px; font-weight: 400; }
        .dhead small { display: block; font-size: 13px; color: var(--secondary-text-color); }
        .close { width: 48px; height: 48px; border: 0; background: none; color: inherit; font-size: 22px; cursor: pointer; border-radius: 24px; }
        .list { display: flex; flex-direction: column; padding: 8px 0 12px; }
        .opt { display: flex; align-items: center; gap: 16px; min-height: 56px; padding: 0 24px; border: 0; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
        .opt.on { background: rgba(3,169,244,0.12); }
        .radio { width: 20px; height: 20px; border-radius: 50%; border: 2px solid var(--secondary-text-color); flex: none; }
        .opt.on .radio { border-color: var(--primary-color); box-shadow: inset 0 0 0 4px var(--card-background-color, #1c1c1c); background: var(--primary-color); }
        .opt small { display: block; font-size: 12px; color: var(--secondary-text-color); }
        .hidden { display: none !important; }
      </style>
      <ha-card>
        <div class="head"><span class="name" id="name">${cfg.matrix != null ? cfg.matrix : "Matrix"}</span><span class="live"><span class="dot off" id="dot"></span><span id="age">connecting</span></span></div>
        <canvas id="c" width="384" height="384" aria-label="What the matrix shows"></canvas>
        <button class="status" id="status" type="button" aria-haspopup="dialog">Loading…</button>
        <div class="bar"><div id="bar" style="width: 0%"></div></div>
        <div id="chips" class="${cfg.picker === "chips" ? "" : "hidden"}"><div class="label">Show now</div><div class="chips" id="chiplist"></div></div>
        <div class="foot ${cfg.preview ? "" : "hidden"}">
          <label>Preview <select id="psel" aria-label="Screen to preview in this card"></select></label>
          <button class="chip" id="pbtn" type="button">Preview here</button>
        </div>
        <dialog id="dlg" aria-labelledby="dtitle">
          <div class="dhead"><button class="close" id="dclose" type="button" aria-label="Close">×</button><div><h2 id="dtitle"></h2><small>Show a screen now</small></div></div>
          <div class="list" id="dlist"></div>
        </dialog>
      </ha-card>`;
    const $ = (id) => this.shadowRoot.getElementById(id);
    $("status").onclick = () => {
      if (cfg.picker === "dialog") $("dlg").showModal();
    };
    $("dclose").onclick = () => $("dlg").close();
    $("pbtn").onclick = () => {
      if (this._mode === "preview") this._mode = "live";
      else {
        this._previewScreen = $("psel").value;
        this._mode = "preview";
      }
      this._update();
    };
    this._update();
  }

  _update() {
    if (!this.shadowRoot) return;
    const $ = (id) => this.shadowRoot.getElementById(id);
    const m = this._m;
    const cfg = this._config;
    $("name").textContent = m ? m.name : cfg.matrix != null ? cfg.matrix : "Matrix";
    $("status").textContent = this._statusText();
    $("status").classList.toggle("err", !!this._error);
    $("status").style.cursor = cfg.picker === "dialog" ? "pointer" : "default";
    if (m) {
      const live = m.age != null && m.age < 5;
      $("dot").classList.toggle("off", !live);
      $("age").textContent = live ? `Live · ${m.age} s ago` : m.enabled ? "no frames" : "off";
      const frac = m.pinned || !m.dwell ? 0 : 1 - m.remaining / m.dwell;
      $("bar").style.width = `${Math.max(0, Math.min(100, frac * 100))}%`;
      const options = [AUTO, ...(this._screens || [])];
      const current = m.pinned || AUTO;
      const chips = $("chiplist");
      if (chips.children.length !== options.length) {
        chips.innerHTML = options.map((s) => `<button class="chip" type="button" data-s="${s}">${s}</button>`).join("");
        for (const b of chips.children) b.onclick = () => this._pin(b.dataset.s);
      }
      for (const b of chips.children) b.classList.toggle("on", b.dataset.s === current);
      const list = $("dlist");
      $("dtitle").textContent = m.name;
      if (list.children.length !== options.length) {
        list.innerHTML = options
          .map((s) => `<button class="opt" type="button" data-s="${s}"><span class="radio"></span><span>${s}<small></small></span></button>`)
          .join("");
        for (const b of list.children)
          b.onclick = () => {
            $("dlg").close();
            this._pin(b.dataset.s);
          };
      }
      for (const b of list.children) {
        b.classList.toggle("on", b.dataset.s === current);
        const inRotation = m.screens.includes(b.dataset.s);
        b.querySelector("small").textContent =
          b.dataset.s === AUTO ? `Rotation: ${m.screens.join(" · ")}` : inRotation ? (b.dataset.s === m.showing ? "Showing now" : "") : "Not in this matrix's rotation; shows until Auto";
      }
      const psel = $("psel");
      if (psel.options.length !== (this._screens || []).length) {
        psel.innerHTML = (this._screens || []).map((s) => `<option>${s}</option>`).join("");
      }
      $("pbtn").textContent = this._mode === "preview" ? "Back to live" : "Preview here";
      $("pbtn").classList.toggle("on", this._mode === "preview");
    }
  }
}

customElements.define("wled-matrix-card", WledMatrixCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "wled-matrix-card",
  name: "WLED Matrix",
  description: "What a WLED matrix is showing, with a picker to show a screen now and an in-card preview.",
});
