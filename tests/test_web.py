"""The live view (web: true). Run from the repo root: python3 -m unittest discover tests"""

import os
import sys
import unittest

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
    def test_register_adds_the_three_routes(self):
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


if __name__ == "__main__":
    unittest.main()
