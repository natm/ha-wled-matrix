"""AppDaemon app: show Home Assistant values on WLED LED matrices, as screens on rotation.

Every `refresh` seconds each matrix's current screen is drawn from the latest states and sent over DDP, so WLED shows
it as live data; if the app stops, WLED goes back to its own effect or preset after its realtime timeout. A screen can
be conditional (`show_if`), a priority interrupt (`priority`, `max_time`, `restart_on`), animated (`frame_rate`) and
dimmed in a `night` window. With `web: true` the matrices can be watched and previewed in a browser.

Each matrix has a sensor in Home Assistant whose state is the screen showing (`sensor.wled_matrix_<name>`, or
`state_entity`), and can be pinned to one screen from a dashboard or the live view: give it a `select_entity`
(an input_select helper) and the app fills its options with `Auto` and every screen; choosing one shows it until
`Auto` is chosen again.

The screen types themselves (what `aircraft:`, `weather:`, `rows:` and the rest draw) live in wm/screens/, one module
each; this file only runs the rotation and the timers. See README.md for the configuration.
"""

import datetime
import random
import re
import time

from appdaemon.plugins.hass.hassapi import Hass

from wm.screens import build
from wm.utils.ddp import DdpSender
from wm.utils.mdi import MdiIcons
from wm.web import LiveView

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None

AUTO = "Auto"  # the input_select option that hands a matrix back to its rotation
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


def state_entity(m):
    """The matrix's sensor: `state_entity`, else sensor.wled_matrix_<name> (or <host>)."""
    return m.get("state_entity") or f"sensor.wled_matrix_{slug(m.get('name', m['host']))}"


def screen_names(m, today):
    """The matrix's screen list for `today` (a date). A plain name stands for itself. A `daily` entry stands for one
    screen a day, so one slot in the rotation changes daily: `{daily: [a, b, c]}` takes them in turn, and
    `{daily: {monday: a, tuesday: b, ...}}` names the screen for each weekday."""
    names = []
    for entry in m["screens"]:
        if isinstance(entry, dict):
            choices = entry["daily"]
            if isinstance(choices, dict):
                names.append({str(k).lower(): v for k, v in choices.items()}[WEEKDAYS[today.weekday()]])
            else:
                names.append(choices[today.toordinal() % len(choices)])
        else:
            names.append(entry)
    return names


def check_screens(m, screens):
    """Raise ValueError unless every entry of the matrix's screen list is a known screen, or a `daily` list of them,
    or a `daily` mapping with a known screen for each of the seven weekdays."""
    for entry in m["screens"]:
        if isinstance(entry, dict):
            forms = "a name, {daily: [names]} or {daily: {monday: name, ...}}"
            where = f"matrix {m['host']}: a screen entry can be {forms}"
            daily = entry.get("daily")
            if list(entry) != ["daily"] or not isinstance(daily, (list, dict)) or not daily:
                raise ValueError(f"{where}, not {entry!r}")
            if isinstance(daily, dict):
                if sorted(str(k).lower() for k in daily) != sorted(WEEKDAYS):
                    raise ValueError(f"{where}; daily needs every weekday once, got {sorted(daily)}")
                names = list(daily.values())
            else:
                names = daily
        else:
            names = [entry]
        for name in names:
            if name not in screens:
                raise ValueError(f"matrix {m['host']}: unknown screen {name!r}")


def matrix_state(m, showing, pinned, next_name, enabled, names=None):
    """(state, attributes) for a matrix's sensor: the screen showing, else `idle` (nothing to show) or `off`.
    `names` is the matrix's screen list for today (see screen_names)."""
    state = showing or ("idle" if enabled else "off")
    attributes = {
        "friendly_name": m.get("name", m["host"]),
        "icon": "mdi:dots-grid",
        "host": m["host"],
        "width": m.get("width", 64),
        "height": m.get("height", 64),
        "screens": list(m["screens"] if names is None else names),
        "pinned": pinned,
        "next": next_name,
        "enabled": enabled,
    }
    return state, attributes


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
            check_screens(m, self.screens)
        self.screen_objects = {name: build(self, name, screen) for name, screen in self.screens.items()}
        self.position = {m["host"]: 0 for m in self.matrices}
        self.elapsed = {m["host"]: 0.0 for m in self.matrices}
        self.interrupt = {}  # (host, screen) -> time the priority screen came up
        self.restart_sig = {}  # (host, screen) -> states of its `restart_on` entities when last checked
        self.pinned = {}  # host -> screen shown instead of the rotation (see pin())
        self.published = {}  # host -> (state, attributes) last written to the matrix's sensor
        self.selects = {}  # input_select entity -> host of the matrix it pins
        self.tz = self.home_timezone()
        self.showing = {}  # host -> screen name drawn last
        self.last_draw = {}  # host -> monotonic time of the last frame sent
        self.mirror = {}  # host -> (monotonic time sent, screen name, pixels): the web page's mirror view
        for m in self.matrices:
            if m.get("select_entity"):
                self.setup_select(m)
        if self.args.get("web"):  # a live view at http://<appdaemon>:5050/app/matrix (AppDaemon's web server)
            LiveView(self).register()
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

    def matrix(self, host):
        return next(m for m in self.matrices if m["host"] == host)

    def names(self, m):
        """The matrix's screens today: `{daily: [...]}` entries resolved to one name (see screen_names)."""
        return screen_names(m, self.now().date())

    def enabled(self, m):
        switch = m.get("enabled_entity")
        return switch is None or self.get_state(switch) == "on"

    # ---------- pinning a screen from Home Assistant or the live view ----------
    def setup_select(self, m):
        """`select_entity`: an input_select helper whose options become Auto + every screen; picking one pins it."""
        entity, host = m["select_entity"], m["host"]
        self.selects[entity] = host
        try:
            self.call_service("input_select/set_options", entity_id=entity, options=[AUTO, *sorted(self.screens)])
        except Exception as err:
            self.log(f"{entity}: can't set its options: {err}", level="WARNING")
        current = self.get_state(entity)
        if current in self.screens:
            self.pinned[host] = current
        self.listen_state(self.on_select, entity)

    def on_select(self, entity, attribute, old, new, **kwargs):
        host = self.selects.get(entity)
        if host is not None and new != old:
            self.pin(host, None if new in (None, AUTO) else new, sync=False)

    def pin(self, host, name, sync=True):
        """Show screen `name` on matrix `host` from the next frame, instead of its rotation, until pinned to None
        (Auto). With `sync`, the matrix's input_select (if any) is set to match."""
        if name is not None and name not in self.screens:
            raise ValueError(f"unknown screen {name!r}")
        m = self.matrix(host)
        if name is None:
            self.pinned.pop(host, None)
        else:
            self.pinned[host] = name
        self.elapsed[host] = 0.0
        if sync and m.get("select_entity"):
            try:
                self.call_service("input_select/select_option", entity_id=m["select_entity"], option=name or AUTO)
            except Exception as err:
                self.log(f"{m['select_entity']}: can't select {name or AUTO}: {err}", level="WARNING")

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
    def rotation(self, m):
        """Indices (into the matrix's screen list) of the screens in its rotation right now."""
        objects = self.screen_objects
        return [i for i, n in enumerate(self.names(m)) if not objects[n].priority and objects[n].visible()]

    def dwell(self, m):
        """Seconds the current screen stays up."""
        return self.screen_objects[self.names(m)[self.position[m["host"]]]].dwell(m.get("dwell", 10))

    def next_screen(self, m):
        """The screen after the current one in the rotation, or None (pinned, or nothing to rotate to)."""
        host = m["host"]
        rotation = self.rotation(m)
        if host in self.pinned or len(rotation) < 2:
            return None
        later = [i for i in rotation if i > self.position[host]]
        return self.names(m)[later[0] if later else rotation[0]]

    def remaining(self, m):
        """Seconds until the rotation moves on (0 when pinned)."""
        host = m["host"]
        return 0.0 if host in self.pinned else max(0.0, self.dwell(m) - self.elapsed[host])

    def choose(self, m):
        """The screen to draw on matrix `m` now."""
        host, names = m["host"], self.names(m)
        pinned = self.pinned.get(host)
        if pinned in self.screens:  # a pick from a dashboard or the live view beats everything else
            return pinned
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
        rotation = self.rotation(m)
        if not rotation:
            return None
        self.elapsed[host] += self.refresh
        current = self.position[host]
        if current not in rotation or (len(rotation) > 1 and self.elapsed[host] >= self.dwell(m)):
            self.elapsed[host] = 0.0
            later = [i for i in rotation if i > current]
            self.position[host] = later[0] if later else rotation[0]
        return names[self.position[host]]

    # ---------- the matrix's sensor in Home Assistant ----------
    def matrix_status(self, m):
        """What the live view and the dashboard card show about a matrix, beyond the frame itself."""
        host = m["host"]
        return {
            "pinned": self.pinned.get(host),
            "next": self.next_screen(m),
            "remaining": round(self.remaining(m), 1),
            "dwell": self.dwell(m),
            "screens": self.names(m),
            "enabled": self.enabled(m),
            "select": m.get("select_entity"),
            "sensor": state_entity(m),
        }

    def publish(self, m, showing):
        """Keep the matrix's sensor current: its state is the screen showing, else idle or off. Written on change."""
        host = m["host"]
        enabled = self.enabled(m)
        current = matrix_state(
            m, showing, self.pinned.get(host), self.next_screen(m) if showing else None, enabled, self.names(m)
        )
        if self.published.get(host) == current:
            return
        self.published[host] = current
        try:
            self.set_state(state_entity(m), state=current[0], attributes=current[1])
        except Exception as err:
            self.log(f"{host}: can't update {state_entity(m)}: {err}", level="WARNING")

    # ---------- drawing ----------
    def tick(self, kwargs):
        night = self.is_night()
        for m in self.matrices:
            host = m["host"]
            name = self.choose(m) if self.enabled(m) else None
            if name is None:
                self.showing.pop(host, None)  # nothing to show: WLED falls back to its own effect after its timeout
            else:
                if self.showing.get(host) != name:
                    self.screen_objects[name].on_show()  # a new visit: `{random: ...}` config values are drawn again
                self.showing[host] = name
                self.draw(m, name, night)
            self.publish(m, name)

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
        return self.render_pixels(self.screen_objects[name], width, height, night)

    def render_pixels(self, screen, width, height, night):
        """Pixels from a screen object (the live view's editor has ones outside the config), dimmed at night."""
        pixels = screen.render(width, height, night=night, t=time.monotonic(), now=self.now())
        if pixels is None:
            return None
        dim = float((self.night or {}).get("brightness", 0.25)) if night else 1.0
        if dim < 1.0:
            pixels = [(int(r * dim), int(g * dim), int(b * dim)) for r, g, b in pixels]
        return pixels
