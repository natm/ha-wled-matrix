"""Power-flow screen and per-screen frame rate. Run from the repo root: python3 -m unittest discover tests"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apps", "wled_matrix"))

import wm_power as wp  # noqa: E402
from wm_text import TEXT, TINY, text_width  # noqa: E402

CFG = {"solar": ["sensor.pv", "sensor.pv_ac"], "soc": "sensor.soc", "battery": "sensor.batt", "load": "sensor.load",
       "ev": "sensor.ev", "grid": "sensor.grid", "max_kw": 10}


def states(**v):
    names = {"pv": "sensor.pv", "pv_ac": "sensor.pv_ac", "soc": "sensor.soc", "batt": "sensor.batt",
             "load": "sensor.load", "ev": "sensor.ev", "grid": "sensor.grid"}
    return {names[k]: str(x) for k, x in v.items()}


def at(px, x, y, w=64):
    return px[y * w + x]


class Readings(unittest.TestCase):
    def test_solar_entities_are_added(self):
        v = wp.readings(CFG, states(pv=7700, pv_ac=4700))
        self.assertEqual(v["solar"], 12400)

    def test_unknown_solar_entity_is_skipped(self):
        v = wp.readings(CFG, {"sensor.pv": "unavailable", "sensor.pv_ac": "300"})
        self.assertEqual(v["solar"], 300)
        self.assertIsNone(wp.readings(CFG, {})["solar"])

    def test_house_is_load_minus_ev_only_when_configured(self):
        s = states(load=10000, ev=6900)
        self.assertEqual(wp.readings(CFG, s)["house"], 10000)
        self.assertEqual(wp.readings({**CFG, "load_includes_ev": True}, s)["house"], 3100)

    def test_house_never_negative_and_ev_unknown_leaves_load(self):
        cfg = {**CFG, "load_includes_ev": True}
        self.assertEqual(wp.readings(cfg, states(load=5000, ev=6000))["house"], 0)
        self.assertEqual(wp.readings(cfg, states(load=5000))["house"], 5000)

    def test_entities_lists_every_one(self):
        self.assertEqual(len(wp.entities(CFG)), 7)


class Formatting(unittest.TestCase):
    def test_kw(self):
        self.assertEqual(wp.kw(12400), "12.4")
        self.assertEqual(wp.kw(-2400), "2.4")
        self.assertEqual(wp.kw(30), "0")
        self.assertEqual(wp.kw(None), "-")

    def test_soc_colours(self):
        self.assertEqual(wp.soc_colour(30, {}), (0, 200, 0))
        self.assertEqual(wp.soc_colour(25, {}), (240, 150, 0))
        self.assertEqual(wp.soc_colour(19, {}), (230, 0, 0))

    def test_speed_grows_with_power_and_caps(self):
        self.assertLess(wp.dot_speed(500, 10000), wp.dot_speed(5000, 10000))
        self.assertEqual(wp.dot_speed(20000, 10000), wp.dot_speed(10000, 10000))


class Layout(unittest.TestCase):
    def test_lines_clear_the_corner_numbers(self):
        """The widest corner numbers ("88.8") must not share a pixel with any line (the mock-up's tight spot)."""
        w = text_width("88.8", TEXT)
        boxes = [(0, 14, w - 1, 20), (63 - w, 14, 62, 20), (63 - w, 56, 62, 62)]
        line = {p for pts in wp.PATHS.values() for p in wp.path_points(pts)}
        for x0, y0, x1, y1 in boxes:
            near = {(x, y) for x in range(x0 - 1, x1 + 2) for y in range(y0 - 1, y1 + 2)}
            self.assertFalse(line & near, (x0, y0))


class Drawing(unittest.TestCase):
    def frame(self, t=0.0, night=False, **v):
        return wp.render_power_flow(CFG, states(**v), 64, 64, None, t=t, night=night)

    def test_idle_line_is_grey_and_still(self):
        a, b = self.frame(t=0, pv=0), self.frame(t=1.3, pv=0)
        line = wp.path_points(wp.PATHS["solar"])
        self.assertTrue(all(at(a, x, y) == tuple(wp.DEFAULT_COLOURS["line"]) for x, y in line))
        self.assertEqual(a, b)

    def test_comets_move_by_day_and_slowly_at_night(self):
        self.assertNotEqual(self.frame(t=0, pv=5000), self.frame(t=0.5, pv=5000))
        # At night the app draws once a second: each second the comets move on by `night_speed` (1 px)...
        self.assertNotEqual(self.frame(t=10, night=True, pv=5000), self.frame(t=11, night=True, pv=5000))
        line = wp.path_points(wp.PATHS["solar"])
        head = tuple(wp.DEFAULT_COLOURS["solar"])

        def first_head(t):
            px = self.frame(t=t, night=True, pv=5000)
            return next(i for i, (x, y) in enumerate(line) if at(px, x, y) == head)
        self.assertEqual(first_head(11), first_head(10) + 1)

    def test_battery_pulse_still_at_night(self):
        def fill_edge(t, night):
            px = self.frame(t=t, night=night, batt=2000, soc=50)
            return [at(px, x, y) for y in range(43, 55) for x in range(2, 11)]
        self.assertNotEqual(fill_edge(0.0, False), fill_edge(0.5, False))
        self.assertEqual(fill_edge(0.0, True), fill_edge(0.5, True))

    def test_comet_tail_fades_behind_the_head(self):
        """Each comet: the head at full colour, then 50 %, 22 % and 10 % behind it, on a 12 % line."""
        line = wp.path_points(wp.PATHS["grid"])
        red = tuple(wp.DEFAULT_COLOURS["import"])
        px = self.frame(t=0, grid=3000)
        colours = [at(px, x, y) for x, y in line]
        heads = [i for i, c in enumerate(colours) if c == red]
        self.assertTrue(heads)
        self.assertTrue(all(b - a == wp.COMET_SPACING for a, b in zip(heads, heads[1:])))
        for h in heads:
            for k, b in enumerate(wp.COMET_TAIL):
                if h - k >= 0:
                    self.assertEqual(colours[h - k], wp.scale(red, b))
        others = set(range(len(line))) - {h - k for h in heads for k in range(len(wp.COMET_TAIL))}
        self.assertTrue(others)
        self.assertTrue(all(colours[i] == wp.scale(red, wp.COMET_LINE) for i in others))

    def test_comets_move_one_or_two_pixels_a_frame(self):
        """At 5 frames a second the comets step 1-2 px, never as much as half the spacing (no wagon-wheel)."""
        for watts in (100, 3000, 10000, 30000):
            step = wp.dot_speed(watts, 10000) / 5
            self.assertGreaterEqual(step, 1)
            self.assertLessEqual(step, 2)
            self.assertLess(step, wp.COMET_SPACING / 2)

    def test_car_line_is_always_the_car_colour(self):
        line = wp.path_points(wp.PATHS["ev"])
        car = tuple(wp.DEFAULT_COLOURS["ev"])
        allowed = {car} | {wp.scale(car, b) for b in wp.COMET_TAIL + (wp.COMET_LINE,)}
        for supply in (dict(pv=9000), dict(grid=9000), dict(batt=-9000), dict(pv=3000, grid=5000)):
            for t in (0, 0.2, 0.4, 0.6):
                px = self.frame(t=t, ev=7000, **supply)
                self.assertTrue({at(px, x, y) for x, y in line} <= allowed, supply)

    def test_kw_label_sits_under_the_house_figure(self):
        """"KW" in the 3x5 font at 45 % of the house white, rows 48-52, clear of a wide house figure ("12.4")."""
        px = self.frame(load=12400)
        dim = wp.scale(wp.DEFAULT_COLOURS["house"], 0.45)
        rows = {y for y in range(64) for x in range(64) if at(px, x, y) == dim}
        self.assertEqual(rows, set(range(48, 53)))
        self.assertGreaterEqual(wp.KW_LABEL_Y, wp.HOUSE_NUMBER_Y + 7 + 3)  # 3 clear rows under the 7-row figure
        w, kw_w = text_width("12.4", TEXT), text_width("KW", TINY)
        number = {(x, y) for x in range(32 - w // 2, 32 - w // 2 + w) for y in range(wp.HOUSE_NUMBER_Y, wp.HOUSE_NUMBER_Y + 7)}
        label = {(x, y) for x in range(32 - kw_w // 2, 32 - kw_w // 2 + kw_w) for y in range(wp.KW_LABEL_Y, wp.KW_LABEL_Y + 5)}
        self.assertFalse(number & label)
        line = {p for pts in wp.PATHS.values() for p in wp.path_points(pts)}
        self.assertFalse(line & label)

    def test_grid_colour_follows_direction(self):
        x, y = wp.PATHS["grid"][0]
        imp = [at(self.frame(t=i / 10, grid=3000), x, y) for i in range(12)]
        exp = [at(self.frame(t=i / 10, grid=-3000), x, y) for i in range(12)]
        self.assertTrue(all(p[0] > p[1] for p in imp))  # red
        self.assertTrue(all(p[1] > p[0] for p in exp))  # green

    def test_dots_flow_towards_the_house_on_import(self):
        """On import the bright dot steps from the pylon towards the house as time passes."""
        line = wp.path_points(wp.PATHS["grid"])
        bright = tuple(wp.DEFAULT_COLOURS["import"])

        def first_dot(t):
            px = self.frame(t=t, grid=2000)
            return next(i for i, (x, y) in enumerate(line) if at(px, x, y) == bright)
        speed = wp.dot_speed(2000, 10000)
        self.assertEqual(first_dot(1 / speed), first_dot(0) + 1)

    def test_export_reverses_the_dots(self):
        line = wp.path_points(wp.PATHS["grid"])[::-1]
        green = (0, 220, 90)

        def first_dot(t):
            px = self.frame(t=t, grid=-2000)
            return next(i for i, (x, y) in enumerate(line) if at(px, x, y) == green)
        speed = wp.dot_speed(2000, 10000)
        self.assertEqual(first_dot(1 / speed), first_dot(0) + 1)

    def test_unknown_values_draw(self):
        px = wp.render_power_flow(CFG, {}, 64, 64, None)
        self.assertEqual(len(px), 64 * 64)


class FrameRate(unittest.TestCase):
    """The app's faster timer redraws only a showing screen with `frame_rate`, and never at night."""

    @classmethod
    def setUpClass(cls):
        hassapi = types.ModuleType("appdaemon.plugins.hass.hassapi")
        hassapi.Hass = object
        for name in ("appdaemon", "appdaemon.plugins", "appdaemon.plugins.hass"):
            sys.modules.setdefault(name, types.ModuleType(name))
        sys.modules["appdaemon.plugins.hass.hassapi"] = hassapi
        import wled_matrix
        cls.mod = wled_matrix

    def app(self, night=False):
        app = self.mod.WledMatrix()
        app.screens = {"flow": {"frame_rate": 5, "power_flow": CFG}, "plain": {"rows": []}}
        app.matrices = [{"host": "a"}, {"host": "b"}]
        app.showing, app.last_draw = {"a": "flow", "b": "plain"}, {}
        app.is_night = lambda: night
        app.drawn = []
        app.draw = lambda m, name, n: app.drawn.append((m["host"], name, n))
        return app

    def test_redraws_only_the_animated_screen(self):
        app = self.app()
        app.fast_tick({})
        self.assertEqual(app.drawn, [("a", "flow", False)])

    def test_not_again_until_the_frame_is_due(self):
        app = self.app()
        app.last_draw["a"] = self.mod.time.monotonic()
        app.fast_tick({})
        self.assertEqual(app.drawn, [])

    def test_nothing_at_night(self):
        app = self.app(night=True)
        app.fast_tick({})
        self.assertEqual(app.drawn, [])


if __name__ == "__main__":
    unittest.main()
