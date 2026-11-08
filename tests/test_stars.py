"""Stars screen (week and alert). Run from the repo root: python3 -m unittest discover tests"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apps", "wled_matrix"))

import wm_stars as ws  # noqa: E402

KIDS = [{"id": "seth", "name": "Seth", "colour": [0, 170, 255], "week": "counter.sw", "year": "counter.sy"},
        {"id": "dylan", "name": "Dylan", "colour": [0, 220, 90], "week": "counter.dw", "year": "counter.dy"}]
WEEK = {"style": "week", "kids": KIDS}
ALERT = {"style": "alert", "alert": "input_text.a", "kids": KIDS}


def st(sw=5, sy=41, dw=3, dy=28, alert=""):
    return {"counter.sw": str(sw), "counter.sy": str(sy), "counter.dw": str(dw), "counter.dy": str(dy),
            "input_text.a": alert}


class Stars(unittest.TestCase):
    def test_entities(self):
        self.assertEqual(len(ws.entities(ALERT)), 5)

    def test_parse_alert(self):
        self.assertEqual(ws.parse_alert("dylan,+"), ("dylan", True))
        self.assertEqual(ws.parse_alert("Seth,-"), ("seth", False))
        self.assertEqual(ws.parse_alert(""), (None, True))

    def test_week_draws_names_in_colour(self):
        px = ws.render_stars(WEEK, st())
        self.assertIn((0, 170, 255), px)
        self.assertIn((0, 220, 90), px)
        self.assertEqual(len(px), 64 * 64)

    def test_unknown_states_draw_zero(self):
        px = ws.render_stars(WEEK, {"counter.sw": "unavailable"})
        self.assertEqual(len(px), 64 * 64)

    def test_alert_plus_minus_and_unknown(self):
        plus = ws.render_stars(ALERT, st(alert="dylan,+"))
        minus = ws.render_stars(ALERT, st(alert="dylan,-"))
        blank = ws.render_stars(ALERT, st(alert="nobody,+"))
        self.assertIn((0, 220, 90), plus)
        self.assertIn(ws.GOLD, plus[:30 * 64])        # WELL DONE in gold, top half
        self.assertNotIn(ws.GOLD, minus[:30 * 64])    # STAR OFF is grey
        self.assertEqual(set(blank), {(0, 0, 0)})

    def test_alert_twinkles_still_at_night(self):
        a = ws.render_stars(ALERT, st(alert="seth,+"), t=0.0, night=True)
        b = ws.render_stars(ALERT, st(alert="seth,+"), t=0.4, night=True)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()


class RestartOn(unittest.TestCase):
    """A priority screen comes back for a fresh max_time when a `restart_on` entity changes, even though its show_if
    entity stayed on (the bug on 2026-11-08: presses after the first 20 s never showed)."""

    @classmethod
    def setUpClass(cls):
        import types
        hassapi = types.ModuleType("appdaemon.plugins.hass.hassapi")
        hassapi.Hass = object
        for name in ("appdaemon", "appdaemon.plugins", "appdaemon.plugins.hass"):
            sys.modules.setdefault(name, types.ModuleType(name))
        sys.modules["appdaemon.plugins.hass.hassapi"] = hassapi
        import wled_matrix
        cls.mod = wled_matrix

    def app(self, restart_on):
        app = self.mod.WledMatrix()
        app.screens = {"week": {"rows": []},
                       "pop": {"priority": True, "show_if": "input_boolean.on", "max_time": 20,
                               **({"restart_on": restart_on} if restart_on else {})}}
        app.matrices = [{"host": "a", "screens": ["week", "pop"]}]
        app.refresh = 1.0
        app.position, app.elapsed, app.interrupt, app.restart_sig = {"a": 0}, {"a": 0.0}, {}, {}
        app.states = {"input_boolean.on": "on", "counter.w": "1"}
        app.get_state = lambda e, **kw: app.states.get(e)
        return app

    def run_at(self, app, t):
        self.mod.time.monotonic = lambda: t
        return app.choose(app.matrices[0])

    def setUp(self):
        self.real = self.mod.time.monotonic

    def tearDown(self):
        self.mod.time.monotonic = self.real

    def test_without_restart_on_a_later_press_is_missed(self):
        app = self.app(None)
        self.assertEqual(self.run_at(app, 100), "pop")
        app.states["counter.w"] = "2"
        self.assertEqual(self.run_at(app, 125), "week")

    def test_restart_on_brings_it_back(self):
        app = self.app(["counter.w"])
        self.assertEqual(self.run_at(app, 100), "pop")
        self.assertEqual(self.run_at(app, 121), "week")      # first 20 s over
        app.states["counter.w"] = "2"                         # another press, boolean still on
        self.assertEqual(self.run_at(app, 125), "pop")
        self.assertEqual(self.run_at(app, 144), "pop")        # a fresh 20 s from 125
        self.assertEqual(self.run_at(app, 146), "week")
