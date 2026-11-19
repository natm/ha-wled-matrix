"""Jungle screen. Run from the repo root: python3 -m unittest discover tests"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apps", "wled_matrix"))

import wm_jungle as wj  # noqa: E402


class Jungle(unittest.TestCase):
    def test_frame_size(self):
        self.assertEqual(len(wj.render_jungle({}, t=3.0)), 64 * 64)

    def test_same_time_same_frame(self):
        self.assertEqual(wj.render_jungle({}, t=12.3), wj.render_jungle({}, t=12.3))

    def test_moves(self):
        self.assertNotEqual(wj.render_jungle({}, t=5.0), wj.render_jungle({}, t=5.4))

    def test_still_at_night(self):
        self.assertEqual(wj.render_jungle({}, t=5.0, night=True), wj.render_jungle({}, t=99.0, night=True))

    def test_creatures_appear(self):
        birds = {look[0] for looks in wj.BIRD_LOOKS.values() for look in looks}
        fur = {look[0] for look in wj.MONKEY_LOOKS}
        seen_bird = seen_monkey = False
        for k in range(0, 60):
            px = set(wj.render_jungle({}, t=k * 0.5))
            seen_bird |= bool(px & birds)
            seen_monkey |= bool(px & fur)
        self.assertTrue(seen_bird)
        self.assertTrue(seen_monkey)

    def test_seed_changes_sequence(self):
        self.assertNotEqual(wj.render_jungle({"seed": 1}, t=8.0), wj.render_jungle({"seed": 2}, t=8.0))


if __name__ == "__main__":
    unittest.main()
