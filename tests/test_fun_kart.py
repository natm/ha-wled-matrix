"""Kart screen. Run from the repo root: python3 -m unittest discover tests"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apps", "wled_matrix"))

import wm_fun_kart as wk  # noqa: E402


class Kart(unittest.TestCase):
    def test_frame_size(self):
        self.assertEqual(len(wk.render_kart({}, t=3.0)), 64 * 64)

    def test_same_time_same_frame(self):
        a = wk.render_kart({}, t=12.3)
        wk.circuit.cache_clear()
        self.assertEqual(a, wk.render_kart({}, t=12.3))

    def test_moves(self):
        self.assertNotEqual(wk.render_kart({}, t=10.0), wk.render_kart({}, t=10.2))

    def test_still_at_night(self):
        self.assertEqual(wk.render_kart({}, t=5.0, night=True), wk.render_kart({}, t=999.0, night=True))

    def test_seed_changes_circuit(self):
        a, b = wk.circuit(1, 0), wk.circuit(2, 0)
        self.assertNotEqual(a["pts"][100], b["pts"][100])
        self.assertNotEqual(wk.render_kart({"seed": 1}, t=20.0), wk.render_kart({"seed": 2}, t=20.0))

    def test_race_runs_three_laps_with_overtakes(self):
        c = wk.circuit(0, 0)
        s_end, _ = wk.progress(0, 0, wk.COUNTDOWN + wk.DRIVE, c["length"])
        self.assertAlmostEqual(s_end, wk.LAPS * c["length"], delta=1.0)
        positions = set()
        for k in range(200):
            s, leads = wk.progress(0, 0, wk.COUNTDOWN + k * wk.DRIVE / 200, c["length"])
            positions.add(1 + sum(1 for lead in leads if lead > 0))
        self.assertGreater(len(positions), 2)          # the player's place changes during the race

    def test_track_closed_and_curvy(self):
        c = wk.circuit(0, 3)
        (x0, y0), (x1, y1) = c["pts"][0], c["pts"][-1]
        self.assertLess(abs(x0 - x1) + abs(y0 - y1), 3)
        curv = [abs(wk.curvature(c["pts"], c["length"], s)) for s in range(0, int(c["length"]), 5)]
        self.assertGreater(max(curv), 0.01)

    def test_fast(self):
        wk.circuit.cache_clear()
        t0 = time.perf_counter()
        wk.render_kart({}, t=3.6e6)                    # includes generating the circuit
        first = time.perf_counter() - t0
        t0 = time.perf_counter()
        for k in range(20):
            wk.render_kart({}, t=3.6e6 + k * 0.2)
        self.assertLess((time.perf_counter() - t0) / 20, 0.05)
        self.assertLess(first, 0.2)


if __name__ == "__main__":
    unittest.main()
