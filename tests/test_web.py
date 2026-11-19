"""The live view (web: true). Run from the repo root: python3 -m unittest discover tests"""

import os
import random
import sys
import unittest

try:
    import yaml  # the editor needs PyYAML, which AppDaemon ships; these tests skip without it
except ImportError:  # pragma: no cover
    yaml = None

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apps", "wled_matrix"))

from wm import web  # noqa: E402


class FrameBytes(unittest.TestCase):
    def test_rgb_in_order(self):
        self.assertEqual(web.frame_bytes([(1, 2, 3), (4, 5, 6)]), bytes([1, 2, 3, 4, 5, 6]))

    def test_the_page_uses_the_routes(self):
        for route in ("/matrix_info", "/matrix_frame"):
            self.assertIn(route, web.PAGE)


class Info(unittest.TestCase):
    def test_each_matrix_with_what_it_shows(self):
        matrices = [{"host": "10.0.0.1", "name": "Kitchen", "width": 32}, {"host": "10.0.0.2"}]
        mirror = {"10.0.0.1": (100.0, "energy", [(0, 0, 0)])}
        out = web.info(matrices, mirror, {"energy": {}, "radar": {}}, now=101.25)
        self.assertEqual(out["screens"], ["energy", "radar"])
        self.assertEqual(
            out["matrices"][0],
            {
                "id": 0,
                "name": "Kitchen",
                "host": "10.0.0.1",
                "width": 32,
                "height": 64,
                "showing": "energy",
                "age": 1.2,
            },
        )
        self.assertEqual(out["matrices"][1]["name"], "10.0.0.2")  # no name: the address
        self.assertIsNone(out["matrices"][1]["showing"])
        self.assertIsNone(out["matrices"][1]["age"])

    def test_status_from_the_app_is_merged_in(self):
        def status(m):
            return {"pinned": "radar" if m["host"] == "b" else None, "next": "x", "remaining": 4.0}

        out = web.info([{"host": "a"}, {"host": "b"}], {}, {}, now=0.0, status=status)
        self.assertIsNone(out["matrices"][0]["pinned"])
        self.assertEqual(out["matrices"][1]["pinned"], "radar")
        self.assertEqual(out["matrices"][1]["remaining"], 4.0)


class Routes(unittest.TestCase):
    def test_register_adds_every_route(self):
        class App:
            routes, logged = [], []

            def register_route(self, handler, name):
                self.routes.append((name, handler.__name__))

            def log(self, message, **kwargs):
                self.logged.append(message)

        app = App()
        web.LiveView(app).register()
        self.assertEqual(
            app.routes,
            [
                ("matrix", "page"),
                ("matrix_info", "info"),
                ("matrix_frame", "frame"),
                ("matrix_pin", "pin"),
                ("matrix_card", "card"),
                ("matrix_yaml", "yaml"),
                ("matrix_scratch", "scratch_route"),
            ],
        )
        self.assertEqual(len(app.logged), 1)

    def test_every_response_allows_the_dashboard_origin(self):
        h = web.headers(X_Screen="energy", X_Width=64)
        self.assertEqual(h["Access-Control-Allow-Origin"], "*")
        self.assertIn("X-Age-Ms", h["Access-Control-Expose-Headers"])
        self.assertEqual(h["Cache-Control"], "no-store")
        self.assertEqual((h["X-Screen"], h["X-Width"]), ("energy", "64"))

    def test_the_card_ships_with_the_app(self):
        source = web.CARD.read_text()
        self.assertIn('customElements.define("wled-matrix-card"', source)
        for route in ("/matrix_info", "/matrix_frame", "/matrix_pin"):
            self.assertIn(route, source)
        for option in ("picker", "preview", "fps"):
            self.assertIn(option, source)


class FakeHost:
    """What a Screen needs from the app (see wm/screens/base.py), with no states."""

    def __init__(self):
        self.args, self.rng, self.mdi, self.objects, self.logged = {}, random.Random(0), None, {}, []

    def get_state(self, entity, attribute=None):
        return None

    def call_service(self, name, **data):
        return {}

    def log(self, message, **kwargs):
        self.logged.append(message)

    def shared(self, key, factory):
        return self.objects.setdefault(key, factory())


@unittest.skipUnless(yaml, "PyYAML not installed")
class EditorYaml(unittest.TestCase):
    def test_a_screen_entry_parses(self):
        self.assertEqual(
            web.parse_screen("aquarium: {fish: 3}\nframe_rate: 5\n"), {"aquarium": {"fish": 3}, "frame_rate": 5}
        )

    def test_problems_are_named(self):
        for text, words in (
            ("aquarium: [", "not valid YAML"),
            ("", "mapping"),
            ("- a\n- b", "mapping"),
            ("just text", "mapping"),
            ("aircraft: {style: radar, coastline: /etc/passwd}", "coastline"),
        ):
            with self.subTest(text=text), self.assertRaises(ValueError) as err:
                web.parse_screen(text)
            self.assertIn(words, str(err.exception))

    def test_configured_screens_round_trip_in_their_own_order(self):
        screen = {"frame_rate": 5, "aquarium": {"fish": {"random": [1, 10]}, "seed": 0}}
        text = web.screen_yaml(screen)
        self.assertTrue(text.startswith("frame_rate: 5\n"))
        self.assertEqual(web.parse_screen(text), screen)

    def test_types_and_templates(self):
        self.assertEqual(web.types()[0], "rows")
        self.assertIn("aquarium", web.types())
        self.assertIn("power_flow", web.types())
        for key in web.types():
            with self.subTest(type=key):
                screen = web.parse_screen(web.template(key))
                self.assertIn(key, screen)
        self.assertIn("docs/screens/power-flow.md", web.template("power_flow"))
        self.assertEqual(web.info([], {}, {}, 0.0)["types"], web.types())


@unittest.skipUnless(yaml, "PyYAML not installed")
class ScratchScreens(unittest.TestCase):
    def setUp(self):
        self.clock = [100.0]
        self.scratch = web.Scratch(FakeHost(), ttl=60, clock=lambda: self.clock[0])

    def test_same_text_same_screen_and_it_renders(self):
        a = self.scratch.add("aquarium: {}\n")
        b = self.scratch.add("aquarium: {}\n")
        c = self.scratch.add("jungle: {}\n")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertIs(self.scratch.get(a), self.scratch.get(b))
        self.assertEqual(len(self.scratch.get(a).render(64, 64, night=False, t=0.0, now=None)), 64 * 64)
        self.assertEqual(self.scratch.get(a).name, "editor")

    def test_bad_configs_fail_at_add(self):
        with self.assertRaises(ValueError) as err:
            self.scratch.add("aquarium: {fish: {random: [1, lots]}}")
        self.assertIn("editor.aquarium.fish", str(err.exception))
        with self.assertRaises(ValueError):
            self.scratch.add("nope")

    def test_unused_screens_expire(self):
        a = self.scratch.add("aquarium: {}\n")
        self.clock[0] += 30
        b = self.scratch.add("blocks: {}\n")
        self.clock[0] += 31  # a is 61 s old, b 31 s
        self.scratch.add("duel: {}\n")  # adding runs the sweep
        self.assertIsNone(self.scratch.get(a))
        self.assertIsNotNone(self.scratch.get(b))

    def test_reroll_draws_random_values_again(self):
        key = self.scratch.add("aquarium: {fish: {random: [1, 100000]}}\n")
        before = self.scratch.get(key).cfg["fish"]
        seen = {self.scratch.reroll(key).cfg["fish"] for _ in range(10)}
        self.assertTrue(len(seen | {before}) > 1)
        self.assertIsNone(self.scratch.reroll("missing"))


if __name__ == "__main__":
    unittest.main()
