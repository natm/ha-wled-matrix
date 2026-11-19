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
        self.assertEqual(app.routes, [("matrix", "page"), ("matrix_info", "info"), ("matrix_frame", "frame")])
        self.assertEqual(len(app.logged), 1)


if __name__ == "__main__":
    unittest.main()
