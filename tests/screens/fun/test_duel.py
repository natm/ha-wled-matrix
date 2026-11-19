"""Duel screen. Run: python3 -m unittest test_duel from the repo root: python3 -m unittest discover tests."""

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "apps", "wled_matrix"))

from wm.screens.fun import duel as wd  # noqa: E402


def frame_ok(px):
    return len(px) == 64 * 64 and all(len(p) == 3 and all(0 <= v <= 255 and isinstance(v, int) for v in p) for p in px)


class Duel(unittest.TestCase):
    def test_frame_size(self):
        for t in (0.0, 3.0, 77.7, 1234.5, 98765.4):
            self.assertTrue(frame_ok(wd.render_duel({}, t=t)))
        self.assertTrue(frame_ok(wd.render_duel(None, t=1.0)))

    def test_same_time_same_frame(self):
        a = wd.render_duel({}, t=12.3)
        wd.render_duel({}, t=500.0)
        wd.render_duel({"seed": 9}, t=12.3)
        self.assertEqual(a, wd.render_duel({}, t=12.3))

    def test_moves(self):
        self.assertNotEqual(wd.render_duel({}, t=5.0), wd.render_duel({}, t=5.4))

    def test_still_at_night(self):
        self.assertEqual(wd.render_duel({}, t=5.0, night=True), wd.render_duel({}, t=99.0, night=True))

    def test_seed_changes_output(self):
        self.assertNotEqual(wd.render_duel({"seed": 1}, t=8.0), wd.render_duel({"seed": 2}, t=8.0))

    def test_fast_enough(self):
        wd.render_duel({}, t=30.0)
        start = time.perf_counter()
        for k in range(20):
            wd.render_duel({}, t=30.0 + k * 0.2)
        self.assertLess((time.perf_counter() - start) / 20, 0.05)

    def test_someone_wins_every_bout_and_the_score_goes_up(self):
        for bout in range(6):
            winner, moves, _ = wd.bout_plan(0, bout)
            end = wd.READY + len(moves) * wd.MOVE
            self.assertLess(end + 3.5, wd.BOUT_SECS)
            self.assertEqual(moves[-1][:2], (winner, True))
            loser = wd.pose(1 - winner, end + 3.0, winner, moves)
            self.assertTrue(loser["down"])  # on the mat
            self.assertFalse(wd.pose(winner, end + 3.0, winner, moves)["down"])
        self.assertEqual(sum(wd.scores(0, wd.SERIES - 1)), wd.SERIES - 1)
        self.assertEqual(wd.scores(0, wd.SERIES), [0, 0])

    def test_both_colours_are_drawn(self):
        px = wd.render_duel({}, t=4.0)
        self.assertIn(wd.RED, px)
        self.assertIn(wd.BLUE, px)


if __name__ == "__main__":
    unittest.main()
