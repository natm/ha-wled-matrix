"""The Screen base class, the registry and build(). Run from the repo root: python3 -m unittest discover tests"""

import datetime
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "apps", "wled_matrix"))

from wm.screens import Screen, build  # noqa: E402
from wm.screens.fun.aquarium import AquariumScreen  # noqa: E402
from wm.screens.items import ItemsScreen  # noqa: E402
from wm.screens.power import PowerFlowScreen  # noqa: E402

NOW = datetime.datetime(2026, 11, 19, 12, 0, tzinfo=datetime.timezone.utc)
FORECAST = [
    {"datetime": "2026-11-19T00:00:00+00:00", "condition": "sunny", "temperature": 10, "templow": 3,
     "precipitation": 0.0, "wind_speed": 12.0, "wind_bearing": 180},
    {"datetime": "2026-11-20T00:00:00+00:00", "condition": "rainy", "temperature": 8, "templow": 4,
     "precipitation": 3.2, "wind_speed": 20.0, "wind_bearing": 225},
]  # fmt: skip


class FakeHost:
    """The surface a screen may use (see wm/screens/base.py), with canned states."""

    def __init__(self, states=None, attrs=None, seed=0):
        self.states = states or {}
        self.attrs = attrs or {}  # (entity, attribute) -> value
        self.args = {}
        self.rng = random.Random(seed)
        self.mdi = None
        self.objects = {}
        self.logged = []

    def get_state(self, entity, attribute=None):
        return self.states.get(entity) if attribute is None else self.attrs.get((entity, attribute))

    def call_service(self, name, **data):
        return {"result": {"response": {data["entity_id"]: {"forecast": FORECAST}}}}

    def log(self, message, **kwargs):
        self.logged.append(message)

    def shared(self, key, factory):
        return self.objects.setdefault(key, factory())

    def now(self):
        return NOW


# One minimal, README-shaped config per screen type, plus the states each needs.
CONFIGS = {
    "rows": ({"rows": [{"icon": "none", "entity": "sensor.a", "format": "percent"}]}, {"sensor.a": "42"}),
    "cells": ({"grid": {"rows": 1, "columns": 2}, "cells": [{"row": 0, "col": 0, "icon": "none", "entity": "sensor.a"},
                                                             {"row": 0, "col": 1, "icon": "none"}]}, {"sensor.a": "7"}),
    "camera": ({"camera": "camera.drive"}, {}),
    "aircraft": ({"aircraft": {"style": "radar", "entity": "sensor.adsb", "latitude": 51.5, "longitude": -0.1}}, {}),
    "power_flow": ({"power_flow": {"solar": "sensor.pv", "grid": "sensor.grid", "soc": "sensor.soc"}},
                   {"sensor.pv": "1200", "sensor.grid": "-300", "sensor.soc": "80"}),
    "network": ({"network": {"style": "big",
                             "links": [{"name": "FTTP", "icon": "none", "down": "sensor.d", "up": "sensor.u"}]}},
                {"sensor.d": "900", "sensor.u": "100"}),
    "stars": ({"stars": {"style": "week",
                         "kids": [{"id": "a", "name": "A", "week": "counter.w", "year": "counter.y"}]}},
              {"counter.w": "3", "counter.y": "40"}),
    "weather": ({"weather": {"weather": "weather.home"}}, {}),
    "tides": ({"tides": {"tides": "sensor.tide", "label": "PORT"}}, {}),
    "aquarium": ({"aquarium": {}}, {}),
    "jungle": ({"jungle": {}}, {}),
    "platformer": ({"platformer": {"seed": 1}}, {}),
    "blocks": ({"blocks": {}}, {}),
    "surf": ({"surf": {}}, {}),
    "quest": ({"quest": {}}, {}),
    "kart": ({"kart": {}}, {}),
    "duel": ({"duel": {}}, {}),
}  # fmt: skip
ATTRS = {
    ("sensor.adsb", "aircraft"): [{"hex": "abc", "flight": "BAW123", "lat": 51.6, "lon": -0.2, "alt_baro": 12000,
                                   "track": 90, "gs": 400}],
    ("sensor.tide", "predictions"): [["2026-11-19T15:00:00", 5.2], ["2026-11-19T21:10:00", 0.8]],
    ("weather.home", "all"): {"attributes": {"temperature_unit": "°C", "wind_speed_unit": "km/h"}},
}  # fmt: skip


class Registry(unittest.TestCase):
    def test_every_documented_type_is_registered(self):
        documented = {"camera", "aircraft", "power_flow", "network", "stars", "weather", "tides",
                      "aquarium", "jungle", "platformer", "blocks", "surf", "quest", "kart", "duel"}  # fmt: skip
        self.assertEqual(set(Screen.registry), documented)

    def test_build_picks_the_type_by_its_key(self):
        host = FakeHost()
        self.assertIsInstance(build(host, "a", {"aquarium": {}, "frame_rate": 5}), AquariumScreen)
        self.assertIsInstance(build(host, "p", {"power_flow": {"grid": "sensor.g"}}), PowerFlowScreen)
        self.assertIsInstance(build(host, "r", {"rows": []}), ItemsScreen)
        self.assertIsInstance(build(host, "c", {"grid": {}, "cells": []}), ItemsScreen)

    def test_every_type_renders_a_full_frame(self):
        for name, (screen, states) in CONFIGS.items():
            with self.subTest(screen=name):
                host = FakeHost(states, ATTRS)
                pixels = build(host, name, screen).render(64, 64, night=False, t=0.0, now=NOW)
                if name == "camera":  # no Pillow or token here: 'nothing to show yet', and a warning once
                    self.assertIsNone(pixels)
                    self.assertEqual(len(host.logged), 1)
                else:
                    self.assertEqual(len(pixels), 64 * 64, name)
                    self.assertTrue(all(len(p) == 3 for p in pixels[:10]))

    def test_entities_are_listed(self):
        host = FakeHost()
        self.assertEqual(
            build(host, "p", CONFIGS["power_flow"][0]).entities(), ["sensor.pv", "sensor.grid", "sensor.soc"]
        )
        self.assertEqual(build(host, "r", CONFIGS["rows"][0]).entities(), ["sensor.a"])
        self.assertEqual(build(host, "w", CONFIGS["weather"][0]).entities(), ["weather.home"])
        self.assertEqual(build(host, "a", CONFIGS["aquarium"][0]).entities(), [])


class GenericOptions(unittest.TestCase):
    def test_defaults(self):
        s = build(FakeHost(), "a", {"aquarium": {}})
        self.assertFalse(s.priority)
        self.assertIsNone(s.show_if)
        self.assertEqual(s.frame_rate, 0)
        self.assertEqual(s.max_time, 60)
        self.assertEqual(s.dwell(10), 10)
        self.assertTrue(s.visible())
        self.assertIsNone(s.restart_signature())

    def test_values_from_the_screen(self):
        host = FakeHost({"input_boolean.x": "off", "counter.a": "1", "counter.b": "2"})
        s = build(host, "a", {"aquarium": {}, "priority": True, "show_if": "input_boolean.x", "max_time": 20,
                              "restart_on": ["counter.a", "counter.b"], "frame_rate": 5, "dwell": 15})  # fmt: skip
        self.assertTrue(s.priority)
        self.assertEqual(s.frame_rate, 5)
        self.assertEqual(s.max_time, 20)
        self.assertEqual(s.dwell(10), 15)
        self.assertFalse(s.visible())
        host.states["input_boolean.x"] = "on"
        self.assertTrue(s.visible())
        self.assertEqual(s.restart_signature(), ("1", "2"))

    def test_an_empty_block_means_defaults(self):
        self.assertEqual(build(FakeHost(), "a", {"aquarium": None}).cfg, {})


class RandomValues(unittest.TestCase):
    SCREEN = {"aquarium": {"fish": {"random": [1, 1000]}, "seed": 3}, "dwell": {"random": [10, 20]}}

    def test_resolved_on_build_and_again_on_each_show(self):
        s = build(FakeHost(seed=1), "tank", self.SCREEN)
        fish, dwells = [s.cfg["fish"]], [s.dwell(0)]
        for _ in range(20):
            s.on_show()
            fish.append(s.cfg["fish"])
            dwells.append(s.dwell(0))
        self.assertTrue(all(isinstance(f, int) and 1 <= f <= 1000 for f in fish))
        self.assertGreater(len(set(fish)), 1)
        self.assertTrue(all(10 <= d <= 20 for d in dwells))
        self.assertEqual(s.cfg["seed"], 3)
        self.assertEqual(s.raw, self.SCREEN)  # the config as written is kept

    def test_a_bad_placeholder_fails_at_build_naming_the_screen(self):
        with self.assertRaises(ValueError) as err:
            build(FakeHost(), "tank", {"aquarium": {"fish": {"random": [1, "lots"]}}})
        self.assertIn("tank.aquarium.fish", str(err.exception))


if __name__ == "__main__":
    unittest.main()
