"""AppDaemon app: show Home Assistant values on WLED LED matrices, as screens of icon + number rows, on rotation.

Each matrix gets a list of screens and a dwell time. Every `refresh` seconds the current screen is drawn from the
latest entity states and sent to the matrix over DDP, so WLED shows it as live data. If the app stops, WLED goes back
to its normal effect or preset after its realtime timeout (about 2.5 s by default).

See README.md for the configuration.
"""

from appdaemon.plugins.hass.hassapi import Hass

from wm_ddp import DdpSender
from wm_render import render_screen


class WledMatrix(Hass):
    def initialize(self):
        self.screens = self.args["screens"]
        self.matrices = self.args["matrices"]
        self.refresh = float(self.args.get("refresh", 1))
        self.sender = DdpSender()
        self.position = {m["host"]: 0 for m in self.matrices}
        self.elapsed = {m["host"]: 0.0 for m in self.matrices}
        for m in self.matrices:
            for name in m["screens"]:
                if name not in self.screens:
                    raise ValueError(f"matrix {m['host']}: unknown screen {name!r}")
        self.run_every(self.tick, "now", self.refresh)
        self.log(f"Driving {len(self.matrices)} matrix(es), refresh {self.refresh}s")

    def value(self, entity):
        state = self.get_state(entity)
        try:
            return float(state)
        except (TypeError, ValueError):
            return None

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
            if len(names) > 1 and self.elapsed[host] >= float(m.get("dwell", 10)):
                self.elapsed[host] = 0.0
                self.position[host] = (self.position[host] + 1) % len(names)
            screen = self.screens[names[self.position[host]]]
            values = [self.value(row["entity"]) for row in screen["rows"]]
            pixels = render_screen(screen, values, m.get("width", 64), m.get("height", 64))
            try:
                self.sender.send(host, pixels)
            except OSError as err:
                self.log(f"{host}: send failed: {err}", level="WARNING")
