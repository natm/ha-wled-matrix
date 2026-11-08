"""AppDaemon app: show Home Assistant values on WLED LED matrices, as screens of icon + number rows, on rotation.

Each matrix gets a list of screens and a dwell time. Every `refresh` seconds the current screen is drawn from the
latest entity states and sent to the matrix over DDP, so WLED shows it as live data. If the app stops, WLED goes back
to its normal effect or preset after its realtime timeout (about 2.5 s by default).

Screens can be conditional (`show_if`: only while an entity is on) or priority (`priority: true`: interrupt the
rotation while their `show_if` entity is on, for at most `max_time` seconds). An optional `night` window dims every
screen and stops flashing and fast animation. A screen with `frame_rate` is redrawn that many times a second while
it's showing (for animation), except at night.

Stars screens show weekly star points for children (`style: week`), or a pop-up when a star changes (`style: alert`).

Network screens show internet speed and the line in use (`style: big`), or a failover alert (`style: alert`).

With `web: true`, AppDaemon's web server also serves a live view of the matrices at `/app/matrix`: a mirror of the
frames being sent, or a preview of any screen drawn on demand.

Weather screens read a weather entity's daily forecast with the `weather.get_forecasts` action every
`forecast_interval` seconds (a local Home Assistant call); tide screens read a list of high and low waters from an
entity's attribute.

See README.md for the configuration.
"""

import asyncio
import datetime
import time

from appdaemon.plugins.hass.hassapi import Hass

from wm_aircraft import AircraftSource, normalise, render_aircraft
from wm_camera import CameraSource
from wm_ddp import DdpSender
from wm_mdi import MdiIcons
from wm_network import entities as network_entities, render_network
from wm_stars import entities as stars_entities, render_stars
from wm_power import entities as power_entities, render_power_flow
from wm_render import items, render_screen
from wm_tides import parse_events, render_tides
from wm_web import PAGE, frame_bytes
from wm_weather import animation_phase, render_weather

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
        # Camera screens fetch stills from Home Assistant's camera proxy (Supervisor URL and token by default).
        self.cameras = CameraSource(self.args.get("ha_url"), self.args.get("ha_token"), log=self.log)
        self.aircraft = AircraftSource(log=self.log)
        self.position = {m["host"]: 0 for m in self.matrices}
        self.elapsed = {m["host"]: 0.0 for m in self.matrices}
        self.interrupt = {}  # (host, screen) -> time the priority screen came up
        for m in self.matrices:
            for name in m["screens"]:
                if name not in self.screens:
                    raise ValueError(f"matrix {m['host']}: unknown screen {name!r}")
        self.tz = self.home_timezone()
        self.showing = {}  # host -> screen name drawn last
        self.forecasts = {}  # weather entity -> (monotonic time fetched, daily forecast list or None)
        self.frames = {}  # (screen, size) -> (key, pixels): a weather frame only changes with its phase and data
        self.last_draw = {}  # host -> monotonic time of the last frame sent
        self.mirror = {}  # host -> (monotonic time sent, screen name, pixels): the web page's mirror view
        if self.args.get("web"):  # a live view at http://<appdaemon>:5050/app/matrix (AppDaemon's web server)
            self.register_route(self.web_page, "matrix")
            self.register_route(self.web_info, "matrix_info")
            self.register_route(self.web_frame, "matrix_frame")
            self.log("Live view: /app/matrix on AppDaemon's web server")
        self.run_every(self.tick, "now", self.refresh)
        rates = [float(s["frame_rate"]) for s in self.screens.values()
                 if float(s.get("frame_rate", 0)) > 1 / self.refresh]
        if rates:  # a faster timer, used only while a screen with `frame_rate` is showing
            self.run_every(self.fast_tick, "now", 1 / max(rates))
        self.log(f"Driving {len(self.matrices)} matrix(es), refresh {self.refresh}s")

    def value(self, entity):
        """The entity's raw state; the renderer turns it into a number or on/off."""
        return self.get_state(entity)

    def enabled(self, m):
        switch = m.get("enabled_entity")
        return switch is None or self.get_state(switch) == "on"

    # ---------- night ----------
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

    def is_night(self):
        if not self.night:
            return False
        now = datetime.datetime.now(self.tz).time() if self.tz else datetime.datetime.now().time()
        start = datetime.time.fromisoformat(str(self.night.get("start", "22:00")))
        end = datetime.time.fromisoformat(str(self.night.get("end", "07:00")))
        return start <= now or now < end if start > end else start <= now < end

    # ---------- which screen ----------
    def shown(self, screen):
        entity = screen.get("show_if")
        return entity is None or self.get_state(entity) == "on"

    def choose(self, m):
        """The screen to draw on matrix `m` now."""
        host, names = m["host"], m["screens"]
        now = time.monotonic()
        for name in names:  # priority screens interrupt while their entity is on, for at most max_time
            screen = self.screens[name]
            if not screen.get("priority"):
                continue
            key = (host, name)
            if self.shown(screen) and "show_if" in screen:
                start = self.interrupt.setdefault(key, now)
                if now - start < float(screen.get("max_time", 60)):
                    return name
            else:
                self.interrupt.pop(key, None)  # off again: it may interrupt next time it comes on
        rotation = [i for i, n in enumerate(names) if not self.screens[n].get("priority") and self.shown(self.screens[n])]
        if not rotation:
            return None
        self.elapsed[host] += self.refresh
        current = self.position[host]
        dwell = float(self.screens[names[current]].get("dwell", m.get("dwell", 10)))
        if current not in rotation or (len(rotation) > 1 and self.elapsed[host] >= dwell):
            self.elapsed[host] = 0.0
            later = [i for i in rotation if i > current]
            self.position[host] = later[0] if later else rotation[0]
        return names[self.position[host]]

    # ---------- drawing ----------
    def aircraft_list(self, cfg):
        if "entity" in cfg:
            items = self.get_state(cfg["entity"], attribute=cfg.get("attribute", "aircraft"))
        else:
            items = self.aircraft.fetch(cfg["url"], cfg.get("headers"))
        home = (cfg.get("latitude", self.get_state("zone.home", attribute="latitude")),
                cfg.get("longitude", self.get_state("zone.home", attribute="longitude")))
        home = tuple(map(float, home)) if None not in home else None
        return normalise(items, cfg, home, float(cfg.get("max_age", 15))), home

    def now(self):
        return datetime.datetime.now(self.tz) if self.tz else datetime.datetime.now().astimezone()

    def forecast(self, cfg):
        """The daily forecast for the screen's weather entity, fetched again every `forecast_interval` seconds
        (or a minute after a failed fetch)."""
        entity = cfg["weather"]
        fetched, days = self.forecasts.get(entity, (None, None))
        now = time.monotonic()
        wait = float(cfg.get("forecast_interval", 900)) if days else 60.0
        if fetched is None or now - fetched >= wait:
            try:
                result = self.call_service("weather/get_forecasts", entity_id=entity,
                                           type=cfg.get("forecast_type", "daily"))
                days = find_forecast(result, entity) or days
            except Exception as err:  # keep the last forecast; try again in a minute
                self.log(f"{entity}: get_forecasts failed: {err}", level="WARNING")
            if days is None:
                self.log(f"{entity}: no forecast returned", level="WARNING")
            self.forecasts[entity] = (now, days)
        return days

    def tick(self, kwargs):
        night = self.is_night()
        for m in self.matrices:
            if not self.enabled(m):
                self.showing.pop(m["host"], None)
                continue
            name = self.choose(m)
            if name is None:
                self.showing.pop(m["host"], None)
                continue  # nothing to show: WLED falls back to its own effect after its timeout
            self.showing[m["host"]] = name
            self.draw(m, name, night)

    def fast_tick(self, kwargs):
        """Extra frames for a showing screen with `frame_rate` (not at night); the rotation stays on `tick`."""
        if self.is_night():
            return
        now = time.monotonic()
        for m in self.matrices:
            name = self.showing.get(m["host"])
            rate = float(self.screens[name].get("frame_rate", 0)) if name else 0
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
        screen = self.screens[name]
        if "camera" in screen:
            pixels = self.cameras.pixels(screen, width, height)
            if pixels is None:
                return None
        elif "aircraft" in screen:
            cfg = screen["aircraft"]
            planes, home = self.aircraft_list(cfg)
            pixels = render_aircraft(cfg, planes, width, height, self.mdi, night=night, home=home, log=self.log)
        elif "power_flow" in screen:
            cfg = screen["power_flow"]
            states = {entity: self.get_state(entity) for _, entity in power_entities(cfg)}
            pixels = render_power_flow(cfg, states, width, height, self.mdi, t=time.monotonic(), night=night)
        elif "network" in screen:
            cfg = screen["network"]
            states = {entity: self.get_state(entity) for entity in network_entities(cfg)}
            pixels = render_network(cfg, states, width, height, self.mdi, t=time.monotonic(), night=night)
        elif "stars" in screen:
            cfg = screen["stars"]
            states = {entity: self.get_state(entity) for entity in stars_entities(cfg)}
            pixels = render_stars(cfg, states, width, height, self.mdi, t=time.monotonic(), night=night)
        elif "weather" in screen:
            cfg = screen["weather"]
            attrs = self.get_state(cfg["weather"], attribute="all") or {}
            attrs = attrs.get("attributes", {}) if isinstance(attrs, dict) else {}
            units = {"temperature": attrs.get("temperature_unit"), "wind_speed": attrs.get("wind_speed_unit")}
            days, now, t = self.forecast(cfg), self.now(), time.monotonic()
            key = (id(days), animation_phase(cfg, t, night), night, now.date(), tuple(units.values()))
            cached = self.frames.get((name, width, height))
            if cached and cached[0] == key:
                pixels = cached[1]
            else:
                pixels = render_weather(cfg, days, now, width, height, t=t, night=night, units=units)
                self.frames[(name, width, height)] = (key, pixels)
        elif "tides" in screen:
            cfg = screen["tides"]
            raw = self.get_state(cfg["tides"], attribute=cfg.get("attribute", "predictions"))
            zone = ZoneInfo(cfg["data_time_zone"]) if cfg.get("data_time_zone") and ZoneInfo else datetime.timezone.utc
            events = parse_events(raw if isinstance(raw, list) else [], cfg, zone)
            now = self.now()
            pixels = render_tides(cfg, events, now, now.tzinfo, width, height)
        else:
            values = [self.value(item["entity"]) if "entity" in item else None for item in items(screen)]
            pixels = render_screen(screen, values, width, height, self.mdi)
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
            matrices.append({"id": i, "name": m.get("name", m["host"]), "host": m["host"],
                             "width": m.get("width", 64), "height": m.get("height", 64),
                             "showing": shown[1] if shown else None,
                             "age": round(now - shown[0], 1) if shown else None})
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
            return web.Response(body=frame_bytes(pixels), content_type="application/octet-stream",
                                headers={"X-Screen": name, "X-Width": str(w), "X-Height": str(h),
                                         "Cache-Control": "no-store"})
        try:
            m = self.matrices[int(q.get("m", 0))]
        except (ValueError, IndexError):
            return web.Response(status=404, text="unknown matrix")
        w, h = m.get("width", 64), m.get("height", 64)
        shown = self.mirror.get(m["host"])
        if not shown:
            return web.Response(status=204, headers={"Cache-Control": "no-store"})
        sent, name, pixels = shown
        return web.Response(body=frame_bytes(pixels), content_type="application/octet-stream",
                            headers={"X-Screen": name, "X-Width": str(w), "X-Height": str(h),
                                     "X-Age-Ms": str(int((time.monotonic() - sent) * 1000)),
                                     "Cache-Control": "no-store"})


def find_forecast(result, entity):
    """The forecast list in a `weather.get_forecasts` reply, wherever AppDaemon's version puts it
    ({"result": {"response": {entity: {"forecast": [...]}}}} in AppDaemon 4.5)."""
    if isinstance(result, dict):
        if entity in result and isinstance(result[entity], dict) and isinstance(result[entity].get("forecast"), list):
            return result[entity]["forecast"]
        for value in result.values():
            found = find_forecast(value, entity)
            if found is not None:
                return found
    return None
