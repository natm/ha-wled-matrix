"""Network screen (big number and failover alert). Run from the repo root: python3 -m unittest discover tests"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apps", "wled_matrix"))

import wm_network as wn  # noqa: E402

CFG = {"style": "big", "backup_active": "binary_sensor.on_backup",
       "links": [{"name": "FTTP", "down": "sensor.f_rx", "up": "sensor.f_tx", "latency": "sensor.f_lat", "max_down": 1800},
                 {"name": "STARLINK", "down": "sensor.s_rx", "up": "sensor.s_tx", "latency": "sensor.s_lat"}]}


def states(backup="off", **v):
    s = {"binary_sensor.on_backup": backup}
    s.update({f"sensor.{k}": str(x) for k, x in v.items()})
    return s


def lit(px, x0, y0, x1, y1, w=64):
    return [px[y * w + x] for y in range(y0, y1 + 1) for x in range(x0, x1 + 1) if px[y * w + x] != (0, 0, 0)]


class Readings(unittest.TestCase):
    def test_main_line(self):
        v = wn.readings(CFG, states(f_rx=850, f_tx=60, f_lat=12, s_rx=0.1, s_tx=0.0))
        self.assertFalse(v["on_backup"])
        self.assertEqual((v["name"], v["down"], v["up"], v["latency"]), ("FTTP", 850, 60, 12))

    def test_backup_when_flag_on(self):
        v = wn.readings(CFG, states("on", f_rx="unavailable", s_rx=120, s_tx=15, s_lat=45))
        self.assertTrue(v["on_backup"])
        self.assertEqual((v["name"], v["down"], v["latency"]), ("STARLINK", 120, 45))

    def test_without_flag_falls_back_when_main_has_no_data(self):
        cfg = dict(CFG)
        del cfg["backup_active"]
        self.assertTrue(wn.readings(cfg, states(f_rx="unavailable", s_rx=120))["on_backup"])
        self.assertFalse(wn.readings(cfg, states(f_rx=5, s_rx=120))["on_backup"])

    def test_entities(self):
        self.assertEqual(len(wn.entities(CFG)), 7)

    def test_speed_text(self):
        self.assertEqual([wn.speed_text(x) for x in (None, 0.93, 58.77, 1029.4)], ["-", "0.9", "59", "1029"])


class Drawing(unittest.TestCase):
    def test_big_draws_download_in_blue_and_fill_bar(self):
        px = wn.render_network(CFG, states(f_rx=900, f_tx=60, f_lat=12))
        self.assertIn(wn.DOWN, lit(px, 0, 10, 63, 34))
        bar = px[62 * 64:63 * 64]
        self.assertEqual(sum(1 for p in bar if p == wn.DOWN), 32)  # 900 of 1800 = half the width

    def test_four_digits_fit(self):
        px = wn.render_network(CFG, states(f_rx=1799, f_tx=110, f_lat=12))
        self.assertEqual(px[20 * 64 + 0], (0, 0, 0))   # nothing touches the edges
        self.assertEqual(px[20 * 64 + 63], (0, 0, 0))

    def test_big_on_backup_flashes_main_down(self):
        s = states("on", f_rx="unavailable", s_rx=120, s_tx=15, s_lat=45)
        on = wn.render_network(CFG, s, t=0.0)
        off = wn.render_network(CFG, s, t=0.5)
        self.assertIn(wn.BAD, lit(on, 0, 58, 63, 63))
        self.assertNotIn(wn.BAD, lit(off, 0, 58, 63, 63))
        self.assertIn(wn.WARN, lit(on, 0, 0, 63, 7))   # line name amber while on the backup

    def test_big_on_backup_steady_at_night(self):
        s = states("on", f_rx="unavailable", s_rx=120, s_tx=15)
        self.assertIn(wn.BAD, lit(wn.render_network(CFG, s, t=0.5, night=True), 0, 58, 63, 63))

    def test_alert_border_and_back(self):
        cfg = dict(CFG, style="alert")
        down = wn.render_network(cfg, states("on", s_rx=120, s_tx=15), t=0.0)
        self.assertEqual(down[0], wn.BAD)
        back = wn.render_network(cfg, states("off", f_rx=500), t=0.0)
        self.assertEqual(back[0], (0, 0, 0))
        self.assertIn(wn.GOOD, lit(back, 0, 38, 63, 50))

    def test_no_links(self):
        self.assertEqual(len(wn.render_network({"links": []}, {})), 64 * 64)


if __name__ == "__main__":
    unittest.main()
