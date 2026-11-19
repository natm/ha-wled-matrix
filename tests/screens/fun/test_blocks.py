"""Blocks screen. Run: python3 -m unittest test_blocks from the repo root: python3 -m unittest discover tests."""

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "apps", "wled_matrix"))

from wm.screens.fun import blocks as wb  # noqa: E402


def frame_ok(px):
    return len(px) == 64 * 64 and all(len(p) == 3 and all(0 <= v <= 255 and isinstance(v, int) for v in p) for p in px)


class Blocks(unittest.TestCase):
    def test_frame_size(self):
        for t in (0.0, 3.0, 77.7, 1234.5, 98765.4):
            self.assertTrue(frame_ok(wb.render_blocks({}, t=t)))
        self.assertTrue(frame_ok(wb.render_blocks(None, t=1.0)))

    def test_same_time_same_frame(self):
        a = wb.render_blocks({}, t=12.3)
        wb.render_blocks({}, t=500.0)
        wb.render_blocks({"seed": 9}, t=12.3)
        self.assertEqual(a, wb.render_blocks({}, t=12.3))

    def test_moves(self):
        self.assertNotEqual(wb.render_blocks({}, t=5.0), wb.render_blocks({}, t=5.4))

    def test_still_at_night(self):
        self.assertEqual(wb.render_blocks({}, t=5.0, night=True), wb.render_blocks({}, t=99.0, night=True))

    def test_seed_changes_output(self):
        self.assertNotEqual(wb.render_blocks({"seed": 1}, t=8.0), wb.render_blocks({"seed": 2}, t=8.0))

    def test_fast_enough(self):
        wb.render_blocks({}, t=30.0)
        start = time.perf_counter()
        for k in range(20):
            wb.render_blocks({}, t=30.0 + k * 0.2)
        self.assertLess((time.perf_counter() - start) / 20, 0.05)

    def test_rows_clear_and_games_restart(self):
        tl = wb.Timeline(0, 0)
        tl.until(wb.SLOT)
        shapes = [r for r in tl.records if r["kind"] is not None]
        self.assertGreater(sum(len(r["cleared"]) for r in shapes), 10)
        self.assertGreaterEqual(sum(1 for r in tl.records if r["kind"] is None), 1)  # at least one restart
        self.assertEqual(tl.records[-1]["end"], wb.SLOT)
        for r in shapes:  # the stack never passes the top
            self.assertFalse(any(r["board"][0]))

    def test_counter_goes_up_when_a_row_clears(self):
        tl = wb.timeline_for(0, 0)
        tl.until(120.0)
        rec = next(r for r in tl.records if r["kind"] is not None and r["cleared"])
        nxt = tl.records[tl.records.index(rec) + 1]
        self.assertEqual(nxt["lines"], rec["lines"] + len(rec["cleared"]))
        flash = wb.render_blocks({}, t=rec["lock"] + wb.LOCK + 0.05)
        self.assertGreater(flash.count((255, 255, 255)), 9 * 8)  # a full white row (the squares' lit corners aside)

    def test_any_frame_on_demand(self):
        a = wb.render_blocks({"seed": 3}, t=250.0)  # straight to a late frame, then again from a fresh cache
        wb._timelines.clear()
        self.assertEqual(a, wb.render_blocks({"seed": 3}, t=250.0))


if __name__ == "__main__":
    unittest.main()
