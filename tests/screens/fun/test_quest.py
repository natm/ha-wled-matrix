"""Quest screen. Run: python3 -m unittest test_quest from the repo root: python3 -m unittest discover tests."""

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "apps", "wled_matrix"))

from wm.screens.fun import quest as wq  # noqa: E402


def frame_ok(px):
    return len(px) == 64 * 64 and all(len(p) == 3 and all(0 <= v <= 255 and isinstance(v, int) for v in p) for p in px)


class Quest(unittest.TestCase):
    def test_frame_size(self):
        for t in (0.0, 3.0, 77.7, 1234.5, 98765.4):
            self.assertTrue(frame_ok(wq.render_quest({}, t=t)))
        self.assertTrue(frame_ok(wq.render_quest(None, t=1.0)))

    def test_same_time_same_frame(self):
        a = wq.render_quest({}, t=12.3)
        wq.render_quest({}, t=500.0)
        wq.render_quest({"seed": 9}, t=12.3)
        self.assertEqual(a, wq.render_quest({}, t=12.3))

    def test_moves(self):
        self.assertNotEqual(wq.render_quest({}, t=5.0), wq.render_quest({}, t=5.4))

    def test_still_at_night(self):
        self.assertEqual(wq.render_quest({}, t=5.0, night=True), wq.render_quest({}, t=99.0, night=True))

    def test_seed_changes_output(self):
        self.assertNotEqual(wq.render_quest({"seed": 1}, t=8.0), wq.render_quest({"seed": 2}, t=8.0))

    def test_fast_enough(self):
        wq.render_quest({}, t=30.0)
        start = time.perf_counter()
        for k in range(20):
            wq.render_quest({}, t=30.0 + k * 0.2)
        self.assertLess((time.perf_counter() - start) / 20, 0.05)

    def test_rooms_are_walkable_and_link_up(self):
        quest = wq.Quest(5, 0)
        quest.until(wq.QUEST_SECS)
        self.assertGreater(len(quest.rooms), 10)
        zaps = pickups = 0
        for room, nxt in zip(quest.rooms, quest.rooms[1:]):
            self.assertEqual(nxt.entry, wq.Room.door(wq.OPPOSITE[room.exit_side], room.exit_at))
            pos = room.entry
            for start, end, kind, a, b, _ in room.segs:
                self.assertEqual(a, pos)  # no teleporting
                if kind == "walk":
                    self.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1)
                    self.assertNotIn(b, room.things)  # never through a tree or a pond
                    self.assertTrue(wq.inside(b) or b in (room.entry, room.exit))
                    pos = b
                zaps += kind == "zap"
            self.assertEqual(pos, room.exit)
            self.assertEqual(room.segs[-1][2], "pan")
            self.assertTrue(1 <= room.energy <= 5)
            pickups += len(room.pickups)
        self.assertGreater(zaps, 5)
        self.assertGreater(pickups, 20)
        self.assertGreater(quest.rooms[-1].coins, 20)

    def test_pip_is_drawn(self):
        for t in (2.0, 9.0, 31.0):
            self.assertIn(wq.PIP_COLS["p"], wq.render_quest({}, t=t))


if __name__ == "__main__":
    unittest.main()
