"""Surf screen. Run: python3 -m unittest test_surf from the repo root: python3 -m unittest discover tests."""

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "apps", "wled_matrix"))

from wm.screens.fun import surf as wsu  # noqa: E402


def frame_ok(px):
    return len(px) == 64 * 64 and all(len(p) == 3 and all(0 <= v <= 255 and isinstance(v, int) for v in p) for p in px)


class Surf(unittest.TestCase):
    def test_frame_size(self):
        for t in (0.0, 3.0, 77.7, 1234.5, 98765.4):
            self.assertTrue(frame_ok(wsu.render_surf({}, t=t)))
        self.assertTrue(frame_ok(wsu.render_surf(None, t=1.0)))

    def test_same_time_same_frame(self):
        a = wsu.render_surf({}, t=12.3)
        wsu.render_surf({}, t=500.0)
        wsu.render_surf({"seed": 9}, t=12.3)
        self.assertEqual(a, wsu.render_surf({}, t=12.3))

    def test_moves(self):
        self.assertNotEqual(wsu.render_surf({}, t=5.0), wsu.render_surf({}, t=5.4))

    def test_still_at_night(self):
        self.assertEqual(wsu.render_surf({}, t=5.0, night=True), wsu.render_surf({}, t=99.0, night=True))

    def test_seed_changes_output(self):
        self.assertNotEqual(wsu.render_surf({"seed": 1}, t=8.0), wsu.render_surf({"seed": 2}, t=8.0))

    def test_fast_enough(self):
        wsu.render_surf({}, t=30.0)
        start = time.perf_counter()
        for k in range(20):
            wsu.render_surf({}, t=30.0 + k * 0.2)
        self.assertLess((time.perf_counter() - start) / 20, 0.05)

    def test_every_style_and_sky(self):
        frames = set()
        for style in wsu.STYLES:
            for sky in list(wsu.SKIES) + ["auto"]:
                px = wsu.render_surf({"wave_style": style, "sky": sky, "wave_size": 1.3}, t=9.0)
                self.assertTrue(frame_ok(px))
                frames.add(tuple(px))
        self.assertEqual(len(frames), len(wsu.STYLES) * len(wsu.SKIES))   # "auto" repeats one sky per style
        self.assertNotEqual(wsu.render_surf({"wave_style": "barrel"}, t=9.0), wsu.render_surf({"wave_style": "rolling"}, t=9.0))
        self.assertNotEqual(wsu.render_surf({"wave_style": "barrel"}, t=9.0), wsu.render_surf({"wave_style": "storm"}, t=9.0))
        self.assertNotEqual(wsu.render_surf({"sky": "day"}, t=9.0), wsu.render_surf({"sky": "sunset"}, t=9.0))
        self.assertEqual(wsu.render_surf({"time_of_day": "night"}, t=9.0), wsu.render_surf({"sky": "night"}, t=9.0))

    def test_size_and_colours(self):
        self.assertNotEqual(wsu.render_surf({"wave_size": 0.7}, t=9.0), wsu.render_surf({"wave_size": 1.3}, t=9.0))
        self.assertIn((1, 2, 3), wsu.render_surf({"board": [1, 2, 3]}, t=9.0))
        self.assertIn((0xAB, 0xCD, 0xEF), wsu.render_surf({"wetsuit": "#abcdef"}, t=9.0))
        self.assertIn(wsu.SURFERS["silver"][0], wsu.render_surf({"surfer": "silver"}, t=9.0))
        self.assertTrue(frame_ok(wsu.render_surf({"wave_style": "nonsense", "sky": "?", "board": "nope"}, t=9.0)))

    def test_wipeouts_setting(self):
        t = 22 * 3 + 20.5                             # late in a ride: a wipeout or a kick-out
        self.assertNotEqual(wsu.render_surf({"wipeouts": 0}, t=t), wsu.render_surf({"wipeouts": 1}, t=t))

    def test_ride_length(self):
        self.assertTrue(frame_ok(wsu.render_surf({"ride_seconds": 14}, t=13.0)))
        self.assertTrue(frame_ok(wsu.render_surf({"ride_seconds": 1}, t=13.0)))


if __name__ == "__main__":
    unittest.main()
