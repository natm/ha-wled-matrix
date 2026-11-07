"""AppDaemon app: show Home Assistant values on WLED LED matrices, as screens of icon + number rows, on rotation.

Each matrix gets a list of screens and a dwell time. Every `refresh` seconds the current screen is drawn from the
latest entity states and sent to the matrix over DDP, so WLED shows it as live data. If the app stops, WLED goes back
to its normal effect or preset after its realtime timeout (about 2.5 s by default).

Screens can be conditional (`show_if`: only while an entity is on) or priority (`priority: true`: interrupt the
rotation while their `show_if` entity is on, for at most `max_time` seconds). An optional `night` window dims every
screen and stops flashing.

See README.md for the configuration.
"""

import datetime
import time

from appdaemon.plugins.hass.hassapi import Hass

from wm_aircraft import AircraftSource, normalise, render_aircraft
from wm_camera import CameraSource
from wm_ddp import DdpSender
from wm_mdi import MdiIcons
from wm_render import items, render_screen

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
        self.run_every(self.tick, "now", self.refresh)
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

    def tick(self, kwargs):
        night = self.is_night()
        dim = float(self.night.get("brightness", 0.25)) if night else 1.0
        for m in self.matrices:
            host = m["host"]
            if not self.enabled(m):
                continue
            name = self.choose(m)
            if name is None:
                continue  # nothing to show: WLED falls back to its own effect after its timeout
            screen = self.screens[name]
            width, height = m.get("width", 64), m.get("height", 64)
            if "camera" in screen:
                pixels = self.cameras.pixels(screen, width, height)
                if pixels is None:
                    continue  # nothing to show yet; WLED falls back to its own effect after its timeout
            elif "aircraft" in screen:
                cfg = screen["aircraft"]
                planes, home = self.aircraft_list(cfg)
                pixels = render_aircraft(cfg, planes, width, height, self.mdi, night=night, home=home, log=self.log)
            else:
                values = [self.value(item["entity"]) if "entity" in item else None for item in items(screen)]
                pixels = render_screen(screen, values, width, height, self.mdi)
            if dim < 1.0:
                pixels = [(int(r * dim), int(g * dim), int(b * dim)) for r, g, b in pixels]
            try:
                self.sender.send(host, pixels)
            except OSError as err:
                self.log(f"{host}: send failed: {err}", level="WARNING")
