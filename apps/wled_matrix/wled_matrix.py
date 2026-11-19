"""AppDaemon app: show Home Assistant values on WLED LED matrices, as screens on rotation.

Every `refresh` seconds each matrix's current screen is drawn from the latest states and sent over DDP, so WLED shows
it as live data; if the app stops, WLED goes back to its own effect or preset after its realtime timeout. A screen can
be conditional (`show_if`), a priority interrupt (`priority`, `max_time`, `restart_on`), animated (`frame_rate`) and
dimmed in a `night` window. With `web: true` the matrices can be watched and previewed in a browser.

The screen types themselves (what `aircraft:`, `weather:`, `rows:` and the rest draw) live in wm/screens/, one module
each; this file only runs the rotation and the timers. See README.md for the configuration.
"""

import asyncio
import datetime
import random
import time

from appdaemon.plugins.hass.hassapi import Hass

from wm.screens import build
from wm.utils.ddp import DdpSender
from wm.utils.mdi import MdiIcons
from wm.web import PAGE, frame_bytes

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None


class WledMatrix(Hass):
    def initialize(self):
        self.screens = self.args["screens"]
        self.matrices = self.args["matrices"]
        self.refresh = float(self.args.get("refresh", 1))
        self.night = self.args.get("night")
        self.sender = DdpSender()
        # Material Design Icons are downloaded once and cached here (not stored in this project).
        self.mdi = MdiIcons(self.args.get("icon_cache", "/config/wled_matrix_cache"), log=self.log)
        self.rng = random.Random()  # draws the `{random: [low, high]}` config values
        self.shared_objects = {}  # see shared()
        for m in self.matrices:
            for name in m["screens"]:
                if name not in self.screens:
                    raise ValueError(f"matrix {m['host']}: unknown screen {name!r}")
        self.screen_objects = {name: build(self, name, screen) for name, screen in self.screens.items()}
        self.position = {m["host"]: 0 for m in self.matrices}
        self.elapsed = {m["host"]: 0.0 for m in self.matrices}
        self.interrupt = {}  # (host, screen) -> time the priority screen came up
        self.restart_sig = {}  # (host, screen) -> states of its `restart_on` entities when last checked
        self.tz = self.home_timezone()
        self.showing = {}  # host -> screen name drawn last
        self.last_draw = {}  # host -> monotonic time of the last frame sent
        self.mirror = {}  # host -> (monotonic time sent, screen name, pixels): the web page's mirror view
        if self.args.get("web"):  # a live view at http://<appdaemon>:5050/app/matrix (AppDaemon's web server)
            self.register_route(self.web_page, "matrix")
            self.register_route(self.web_info, "matrix_info")
            self.register_route(self.web_frame, "matrix_frame")
            self.log("Live view: /app/matrix on AppDaemon's web server")
        for screen in self.screen_objects.values():
            screen.start()  # timers or listeners a screen type runs in the background
        self.run_every(self.tick, "now", self.refresh)
        rates = [s.frame_rate for s in self.screen_objects.values() if s.frame_rate > 1 / self.refresh]
        if rates:  # a faster timer, used only while a screen with `frame_rate` is showing
            self.run_every(self.fast_tick, "now", 1 / max(rates))
        self.log(f"Driving {len(self.matrices)} matrix(es), refresh {self.refresh}s")

    def shared(self, key, factory):
        """One object per app for `key`, made by `factory()` the first time: fetchers that screens share, so a camera
        or a receiver is read once per tick however many screens and matrices use it."""
        if key not in self.shared_objects:
            self.shared_objects[key] = factory()
        return self.shared_objects[key]

    def enabled(self, m):
        switch = m.get("enabled_entity")
        return switch is None or self.get_state(switch) == "on"

    # ---------- time and night ----------
    def home_timezone(self):
        name = (self.night or {}).get("time_zone")
        if not name:
            try:
                name = self.get_plugin_config().get("time_zone")
            except Exception:
                name = None
        if name and ZoneInfo:
            try:
                return ZoneInfo(name)
            except Exception:
                self.log(f"unknown time zone {name!r}; night times use the system clock", level="WARNING")
        return None

    def now(self):
        return datetime.datetime.now(self.tz) if self.tz else datetime.datetime.now().astimezone()

    def is_night(self):
        if not self.night:
            return False
        now = datetime.datetime.now(self.tz).time() if self.tz else datetime.datetime.now().time()
        start = datetime.time.fromisoformat(str(self.night.get("start", "22:00")))
        end = datetime.time.fromisoformat(str(self.night.get("end", "07:00")))
        return start <= now or now < end if start > end else start <= now < end

    # ---------- which screen ----------
    def choose(self, m):
        """The screen to draw on matrix `m` now."""
        host, names = m["host"], m["screens"]
        now = time.monotonic()
        for name in names:  # priority screens interrupt while their entity is on, for at most max_time
            screen = self.screen_objects[name]
            if not screen.priority:
                continue
            key = (host, name)
            if screen.show_if is not None and screen.visible():
                start = self.interrupt.setdefault(key, now)
                # `restart_on`: a change to any of these entities while the screen is on starts it again (e.g. a
                # second star pressed while the first pop-up is still up and its show_if entity never went off).
                sig = screen.restart_signature()
                if sig is not None:
                    if self.restart_sig.get(key, sig) != sig:
                        start = self.interrupt[key] = now
                    self.restart_sig[key] = sig
                if now - start < screen.max_time:
                    return name
            else:
                self.interrupt.pop(key, None)  # off again: it may interrupt next time it comes on
                self.restart_sig.pop(key, None)
        rotation = [
            i for i, n in enumerate(names) if not self.screen_objects[n].priority and self.screen_objects[n].visible()
        ]
        if not rotation:
            return None
        self.elapsed[host] += self.refresh
        current = self.position[host]
        dwell = self.screen_objects[names[current]].dwell(m.get("dwell", 10))
        if current not in rotation or (len(rotation) > 1 and self.elapsed[host] >= dwell):
            self.elapsed[host] = 0.0
            later = [i for i in rotation if i > current]
            self.position[host] = later[0] if later else rotation[0]
        return names[self.position[host]]

    # ---------- drawing ----------
    def tick(self, kwargs):
        night = self.is_night()
        for m in self.matrices:
            host = m["host"]
            if not self.enabled(m):
                self.showing.pop(host, None)
                continue
            name = self.choose(m)
            if name is None:
                self.showing.pop(host, None)
                continue  # nothing to show: WLED falls back to its own effect after its timeout
            if self.showing.get(host) != name:
                self.screen_objects[name].on_show()  # a new visit: `{random: ...}` config values are drawn again
            self.showing[host] = name
            self.draw(m, name, night)

    def fast_tick(self, kwargs):
        """Extra frames for a showing screen with `frame_rate` (not at night); the rotation stays on `tick`."""
        if self.is_night():
            return
        now = time.monotonic()
        for m in self.matrices:
            name = self.showing.get(m["host"])
            rate = self.screen_objects[name].frame_rate if name else 0
            if rate > 0 and now - self.last_draw.get(m["host"], float("-inf")) >= 0.9 / rate:
                self.draw(m, name, False)

    def draw(self, m, name, night):
        """Draw screen `name` on matrix `m` and send it."""
        host = m["host"]
        pixels = self.render(name, m.get("width", 64), m.get("height", 64), night)
        if pixels is None:
            return  # nothing to show yet; WLED falls back to its own effect after its timeout
        self.last_draw[host] = time.monotonic()
        self.mirror[host] = (time.monotonic(), name, pixels)  # for the web page's mirror view
        try:
            self.sender.send(host, pixels)
        except OSError as err:
            self.log(f"{host}: send failed: {err}", level="WARNING")

    def render(self, name, width, height, night):
        """Pixels for screen `name` (dimmed at night), or None when there's nothing to show yet (a camera)."""
        pixels = self.screen_objects[name].render(width, height, night=night, t=time.monotonic(), now=self.now())
        if pixels is None:
            return None
        dim = float((self.night or {}).get("brightness", 0.25)) if night else 1.0
        if dim < 1.0:
            pixels = [(int(r * dim), int(g * dim), int(b * dim)) for r, g, b in pixels]
        return pixels

    # ---------- web page (optional: `web: true`) ----------
    async def web_page(self, request, kwargs):
        from aiohttp import web  # AppDaemon ships aiohttp; imported here so tests run without it

        return web.Response(text=PAGE, content_type="text/html")

    async def web_info(self, request, kwargs):
        from aiohttp import web  # AppDaemon ships aiohttp; imported here so tests run without it

        now = time.monotonic()
        matrices = []
        for i, m in enumerate(self.matrices):
            shown = self.mirror.get(m["host"])
            matrices.append(
                {
                    "id": i,
                    "name": m.get("name", m["host"]),
                    "host": m["host"],
                    "width": m.get("width", 64),
                    "height": m.get("height", 64),
                    "showing": shown[1] if shown else None,
                    "age": round(now - shown[0], 1) if shown else None,
                }
            )
        return web.json_response({"matrices": matrices, "screens": sorted(self.screens)})

    async def web_frame(self, request, kwargs):
        """Raw RGB bytes, row by row. ?mode=mirror&m=<index>: the last frame sent to that matrix.
        ?mode=preview&screen=<name>&night=0|1&w=64&h=64: that screen drawn now from live states."""
        from aiohttp import web  # AppDaemon ships aiohttp; imported here so tests run without it

        q = request.query
        if q.get("mode") == "preview":
            name = q.get("screen")
            if name not in self.screens:
                return web.Response(status=404, text="unknown screen")
            w, h = int(q.get("w", 64)), int(q.get("h", 64))
            night = q.get("night") == "1"
            loop = asyncio.get_running_loop()
            pixels = await loop.run_in_executor(None, self.render, name, w, h, night)
            if pixels is None:
                pixels = [(0, 0, 0)] * (w * h)
            return web.Response(
                body=frame_bytes(pixels),
                content_type="application/octet-stream",
                headers={"X-Screen": name, "X-Width": str(w), "X-Height": str(h), "Cache-Control": "no-store"},
            )
        try:
            m = self.matrices[int(q.get("m", 0))]
        except (ValueError, IndexError):
            return web.Response(status=404, text="unknown matrix")
        w, h = m.get("width", 64), m.get("height", 64)
        shown = self.mirror.get(m["host"])
        if not shown:
            return web.Response(status=204, headers={"Cache-Control": "no-store"})
        sent, name, pixels = shown
        return web.Response(
            body=frame_bytes(pixels),
            content_type="application/octet-stream",
            headers={
                "X-Screen": name,
                "X-Width": str(w),
                "X-Height": str(h),
                "X-Age-Ms": str(int((time.monotonic() - sent) * 1000)),
                "Cache-Control": "no-store",
            },
        )
