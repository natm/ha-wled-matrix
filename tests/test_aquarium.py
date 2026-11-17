"""Aquarium screen. Run from the repo root: python3 -m unittest discover tests"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apps", "wled_matrix"))

import wm_aquarium as wa  # noqa: E402


class Aquarium(unittest.TestCase):
    def test_frame_size(self):
        self.assertEqual(len(wa.render_aquarium({}, t=3.0)), 64 * 64)

    def test_same_time_same_frame(self):
        self.assertEqual(wa.render_aquarium({}, t=12.3), wa.render_aquarium({}, t=12.3))

    def test_moves(self):
        self.assertNotEqual(wa.render_aquarium({}, t=5.0), wa.render_aquarium({}, t=5.5))

    def test_still_at_night(self):
        self.assertEqual(wa.render_aquarium({}, t=5.0, night=True), wa.render_aquarium({}, t=99.0, night=True))

    def test_fish_are_random_between_visits(self):
        looks = {(v["sprite"], v["palette"]["b"], v["direction"]) for v in (wa.visit(0, s, 0) for s in range(30))}
        self.assertGreater(len(looks), 10)

    def test_some_fish_on_screen(self):
        water = {wa.water(y, 58) for y in range(64)}
        for t in (3.0, 20.0, 47.0):
            px = wa.render_aquarium({}, t=t)
            fishy = [p for p in px if p in {wa.scale(col, k / 100) for col in wa.COLOURS for k in range(70, 101)}]
            self.assertTrue(fishy, t)
        self.assertTrue(water)


if __name__ == "__main__":
    unittest.main()
