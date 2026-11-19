"""Platformer screen. Run from the repo root: python3 -m unittest discover tests."""

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "apps", "wled_matrix"))

from wm.screens.fun import platformer as wpl  # noqa: E402


def frame_ok(px):
    return len(px) == 64 * 64 and all(len(p) == 3 and all(0 <= v <= 255 and isinstance(v, int) for v in p) for p in px)


class Platformer(unittest.TestCase):
    def test_frame_size(self):
        for t in (0.0, 3.0, 77.7, 1234.5, 98765.4):
            self.assertTrue(frame_ok(wpl.render_platformer({}, t=t)))
        self.assertTrue(frame_ok(wpl.render_platformer(None, t=1.0)))

    def test_same_time_same_frame(self):
        a = wpl.render_platformer({}, t=12.3)
        wpl.render_platformer({}, t=500.0)
        wpl.render_platformer({"seed": 9}, t=12.3)
        self.assertEqual(a, wpl.render_platformer({}, t=12.3))

    def test_moves(self):
        self.assertNotEqual(wpl.render_platformer({}, t=5.0), wpl.render_platformer({}, t=5.4))

    def test_still_at_night(self):
        self.assertEqual(wpl.render_platformer({}, t=5.0, night=True), wpl.render_platformer({}, t=99.0, night=True))

    def test_seed_changes_output(self):
        self.assertNotEqual(wpl.render_platformer({"seed": 1}, t=8.0), wpl.render_platformer({"seed": 2}, t=8.0))

    def test_fast_enough(self):
        wpl.render_platformer({}, t=30.0)
        start = time.perf_counter()
        for k in range(20):
            wpl.render_platformer({}, t=30.0 + k * 0.2)
        self.assertLess((time.perf_counter() - start) / 20, 0.05)

    def test_score_goes_up_and_restarts_each_stage(self):
        st = wpl.stage_for(0, 0)
        self.assertGreater(st.totals[-1], 20)
        self.assertEqual(st.totals, sorted(st.totals))
        self.assertNotEqual(wpl.stage_for(0, 0).items, wpl.stage_for(0, 1).items)  # a new layout every stage

    def test_fox_runs_jumps_and_never_falls_in(self):
        for number in range(3):
            st = wpl.stage_for(4, number)
            jumped = False
            for x in range(0, wpl.STAGE_LEN):
                y, air = st.path(x, st.pieces)
                jumped |= air != 0
                ground = st.top[x + wpl.PAD]
                if air == 0:  # running: on the ground or on a plank, never over a gap
                    on_plank = any(a <= x < b and py == y for a, b, py in st.planks)
                    self.assertTrue(on_plank or ground == y, (number, x, y, ground))
                elif ground is not None:  # in the air: never below the ground under him
                    self.assertLessEqual(y, ground + 0.01, (number, x))
            self.assertTrue(jumped)

    def test_fox_is_drawn(self):
        for t in (2.0, 9.0, 31.0):
            self.assertIn(wpl.FOX["o"], wpl.render_platformer({}, t=t))


if __name__ == "__main__":
    unittest.main()
