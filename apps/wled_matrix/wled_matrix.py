"""AppDaemon app: show Home Assistant values on WLED LED matrices, as screens of icon + number rows, on rotation.

Each matrix gets a list of screens and a dwell time. Every `refresh` seconds the current screen is drawn from the
latest entity states and sent to the matrix over DDP, so WLED shows it as live data. If the app stops, WLED goes back
to its normal effect or preset after its realtime timeout (about 2.5 s by default).

See README.md for the configuration.
"""

from appdaemon.plugins.hass.hassapi import Hass

from wm_camera import CameraSource
from wm_ddp import DdpSender
from wm_mdi import MdiIcons
from wm_render import items, render_screen


class WledMatrix(Hass):
    def initialize(self):
        self.screens = self.args["screens"]
        self.matrices = self.args["matrices"]
        self.refresh = float(self.args.get("refresh", 1))
        self.sender = DdpSender()
        # Material Design Icons are downloaded once and cached here (not stored in this project).
        self.mdi = MdiIcons(self.args.get("icon_cache", "/config/wled_matrix_cache"), log=self.log)
        # Camera screens fetch stills from Home Assistant's camera proxy (Supervisor URL and token by default).
        self.cameras = CameraSource(self.args.get("ha_url"), self.args.get("ha_token"), log=self.log)
        self.position = {m["host"]: 0 for m in self.matrices}
        self.elapsed = {m["host"]: 0.0 for m in self.matrices}
        for m in self.matrices:
            for name in m["screens"]:
                if name not in self.screens:
                    raise ValueError(f"matrix {m['host']}: unknown screen {name!r}")
        self.run_every(self.tick, "now", self.refresh)
        self.log(f"Driving {len(self.matrices)} matrix(es), refresh {self.refresh}s")

    def value(self, entity):
        """The entity's raw state; the renderer turns it into a number or on/off."""
        return self.get_state(entity)

    def enabled(self, m):
        switch = m.get("enabled_entity")
        return switch is None or self.get_state(switch) == "on"

    def tick(self, kwargs):
        for m in self.matrices:
            host = m["host"]
            if not self.enabled(m):
                continue
            names = m["screens"]
            self.elapsed[host] += self.refresh
            # A screen can set its own `dwell` (e.g. longer for a camera), else the matrix's.
            dwell = float(self.screens[names[self.position[host]]].get("dwell", m.get("dwell", 10)))
            if len(names) > 1 and self.elapsed[host] >= dwell:
                self.elapsed[host] = 0.0
                self.position[host] = (self.position[host] + 1) % len(names)
            screen = self.screens[names[self.position[host]]]
            width, height = m.get("width", 64), m.get("height", 64)
            if "camera" in screen:
                pixels = self.cameras.pixels(screen, width, height)
                if pixels is None:
                    continue  # nothing to show yet; WLED falls back to its own effect after its timeout
            else:
                values = [self.value(item["entity"]) if "entity" in item else None for item in items(screen)]
                pixels = render_screen(screen, values, width, height, self.mdi)
            try:
                self.sender.send(host, pixels)
            except OSError as err:
                self.log(f"{host}: send failed: {err}", level="WARNING")
