"""What a screen is.

A screen type is one module in this package with one `Screen` subclass. The subclass names the config key that
selects it (`key = "aircraft"`) and implements `render()`; defining the class is all it takes to register it, as long
as the module is imported from `wm/screens/__init__.py` (one line there). The rows/cells screen has no key and is the
fallback.

The app builds one instance per named entry under `screens:` in apps.yaml and asks it for frames. Everything a screen
needs from the outside comes through `host` (the AppDaemon app, or a fake in tests):

    host.get_state(entity, attribute=None)   host.call_service(name, **data)   host.log(message, level=...)
    host.mdi                                 host.args (the app's config)      host.rng (a random.Random)
    host.shared(key, factory)                host.now() (aware datetime in Home Assistant's time zone)
    host.run_every / host.listen_state       (AppDaemon's own, for screens that do work in the background)

so a screen never imports AppDaemon. The pixel drawing itself stays in plain functions of (cfg, data, width, height,
...) that the tests call directly; `render()` is the few lines that gather the data and call them.
"""

from ..utils.config import resolve


class Screen:
    key = None  # the config key that selects this type; None for the fallback rows/cells screen
    registry = {}  # key -> Screen subclass, filled in as subclasses are defined

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.key is not None:
            Screen.registry[cls.key] = cls

    def __init__(self, host, name, screen):
        self.host, self.name = host, name
        self.raw = screen  # the config as written, placeholders included
        self.screen = self.cfg = None  # set by on_show()
        self.on_show()

    def __repr__(self):
        return f"<{type(self).__name__} {self.name!r}>"

    # ---------- lifecycle ----------
    def start(self):
        """Called once when the app starts, after every screen is built. For timers (`self.host.run_every`) or state
        listeners (`self.host.listen_state`) a screen wants to run in the background; most screens need none."""

    def on_show(self):
        """Called when a matrix starts showing this screen. Draws every `{random: [low, high]}` in the config again,
        so `self.screen` (the whole entry) and `self.cfg` (this type's block, `screen[key]`) hold plain values."""
        self.screen = resolve(self.raw, self.host.rng, self.name)
        cfg = self.screen.get(self.key) if self.key else self.screen
        self.cfg = {} if cfg is None else cfg  # `aquarium:` with nothing under it means defaults

    # ---------- what every screen type implements ----------
    def entities(self):
        """The entities this screen reads; optional, for validation and later for state listeners."""
        return []

    def render(self, width, height, *, night, t, now):
        """Pixels (a list of (r, g, b), row by row, width * height long), or None for 'nothing to show yet'.

        `night` is the app's night window, `t` is time.monotonic() for animation, `now` an aware local datetime.
        """
        raise NotImplementedError

    # ---------- the generic options, read in one place ----------
    @property
    def priority(self):
        return bool(self.screen.get("priority"))

    @property
    def show_if(self):
        return self.screen.get("show_if")

    @property
    def frame_rate(self):
        return float(self.screen.get("frame_rate", 0))

    @property
    def max_time(self):
        return float(self.screen.get("max_time", 60))

    def dwell(self, default):
        return float(self.screen.get("dwell", default))

    def visible(self):
        """True unless `show_if` names an entity that isn't on."""
        return self.show_if is None or self.state(self.show_if) == "on"

    def restart_signature(self):
        """The states of the `restart_on` entities, or None when the screen has none."""
        watch = self.screen.get("restart_on") or []
        if not watch:
            return None
        return tuple(self.state(e) for e in ([watch] if isinstance(watch, str) else watch))

    # ---------- host services ----------
    def state(self, entity, attribute=None):
        if attribute is None:
            return self.host.get_state(entity)
        return self.host.get_state(entity, attribute=attribute)

    def states(self, entities):
        """{entity: state} for the given entities."""
        return {e: self.host.get_state(e) for e in entities}

    def call_service(self, name, **data):
        return self.host.call_service(name, **data)

    def log(self, message, **kwargs):
        self.host.log(message, **kwargs)

    @property
    def mdi(self):
        return self.host.mdi

    def option(self, name, default=None):
        """An app-level option from apps.yaml (e.g. `ha_url`)."""
        return self.host.args.get(name, default)

    def shared(self, key, factory):
        """One object per app for `key`, made by `factory()` the first time: a fetcher that screens share so a source
        is read once per tick however many screens and matrices use it."""
        return self.host.shared(key, factory)


def build(host, name, screen):
    """The Screen for one `screens:` entry: the type whose key is in the config, else the rows/cells screen."""
    for key, cls in Screen.registry.items():
        if key in screen:
            return cls(host, name, screen)
    from .items import ItemsScreen  # here, not at the top: items.py imports this module

    return ItemsScreen(host, name, screen)
