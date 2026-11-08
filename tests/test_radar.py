"""Radar aircraft markers. Run from the repo root: python3 -m unittest discover tests"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apps", "wled_matrix"))

import wm_aircraft as wa  # noqa: E402
from wm_render import Canvas  # noqa: E402

RED = (200, 0, 0)
GREY = (150, 150, 150)


def lit(c):
    return {(i % c.w, i // c.w): v for i, v in enumerate(c.px) if v != (0, 0, 0)}


def marker(kind, track, x=20, y=20, colour=RED):
    c = Canvas(40, 40)
    wa.draw_marker(c, kind, track, x, y, colour)
    return lit(c)


def plane(km, bearing, track, alt=10000, reason=""):
    return {"flight": "T", "hex": "", "km": km, "bearing": bearing, "alt": alt, "on_ground": False,
            "track": track, "gs": 400, "category": None, "squawk": None, "route": "", "type": "", "reason": reason}


class ArrowTest(unittest.TestCase):
    def test_north_arrow_points_up(self):
        px = marker("arrow", 0)
        self.assertEqual(px[(20, 18)], RED)  # tip, full colour
        self.assertEqual(px[(20, 22)], tuple(int(v * wa.SHAFT) for v in RED))  # end of the dim shaft
        self.assertTrue(all(18 <= x <= 22 and 18 <= y <= 22 for x, y in px))  # fits 5 x 5

    def test_snaps_to_eight_headings(self):
        self.assertEqual(marker("arrow", 80), marker("arrow", 90))
        self.assertEqual(marker("arrow", 30), marker("arrow", 45))
        self.assertEqual(marker("arrow", 350), marker("arrow", 0))

    def test_headings_are_rotations(self):
        east, south, west = marker("arrow", 90), marker("arrow", 180), marker("arrow", 270)
        self.assertEqual(east[(22, 20)], RED)
        self.assertEqual(south[(20, 22)], RED)
        self.assertEqual(west[(18, 20)], RED)
        self.assertEqual(marker("arrow", 135)[(22, 22)], RED)  # south-east tip in the corner

    def test_no_track_is_a_dot(self):
        self.assertEqual(set(marker("arrow", None)), {(20, 20), (21, 20), (20, 21), (21, 21)})


class LineTest(unittest.TestCase):
    def test_line_nose_body_tail(self):
        px = marker("line", 90)  # flying east: nose on the right, tail fading to the left
        self.assertEqual(len(px), 5)
        self.assertEqual(px[(20, 20)], RED)
        self.assertGreater(min(px[(21, 20)]), 200)  # white-ish nose
        self.assertEqual(px[(17, 20)], tuple(int(v * 0.12) for v in RED))

    def test_tick_still_available(self):
        px = marker("tick", 0)  # the old look: 2 x 2 dot plus dim pixels ahead
        self.assertTrue({(20, 20), (21, 20), (20, 21), (21, 21)} <= set(px))
        self.assertTrue(any(y < 20 for _, y in px))


class FallbackTest(unittest.TestCase):
    def test_default_arrow(self):
        self.assertEqual(wa.radar_marker({}, 3), "arrow")
        self.assertEqual(wa.radar_marker({"marker": "nonsense"}, 3), "arrow")

    def test_line_when_crowded(self):
        self.assertEqual(wa.radar_marker({}, 12), "arrow")
        self.assertEqual(wa.radar_marker({}, 13), "line")
        self.assertEqual(wa.radar_marker({"line_above": 5}, 6), "line")
        self.assertEqual(wa.radar_marker({"line_above": 0}, 99), "arrow")
        self.assertEqual(wa.radar_marker({"line_above": None}, 99), "arrow")

    def test_explicit_line(self):
        self.assertEqual(wa.radar_marker({"marker": "line"}, 1), "line")
        self.assertEqual(wa.radar_marker({"marker": "tick"}, 99), "tick")


class RadarTest(unittest.TestCase):
    def render(self, planes, **cfg):
        cfg = dict({"style": "radar", "range_km": 100, "show_count": False, "show_range": False}, **cfg)
        px = wa.render_aircraft(cfg, planes, 64, 64)
        return {(i % 64, i // 64): v for i, v in enumerate(px)}

    def test_box_does_not_cover_arrow(self):
        # Interesting plane due east of home, heading north: arrow tip must be drawn, box 7 x 7 round it
        px = self.render([plane(50, 90, 0, reason="low flyer")], rings_km=[])
        x, y = 32 + 15, 32
        colour = wa.band_colour(10000, {})
        self.assertEqual(px[(x, y - 2)], colour)  # tip
        self.assertEqual(px[(x - 3, y - 3)], tuple(wa.DEFAULT_COLOURS["marker"]))
        self.assertEqual(px[(x + 3, y + 3)], tuple(wa.DEFAULT_COLOURS["marker"]))

    def test_marker_drawn_over_box(self):
        # A line marker's tail reaches the box edge: the marker wins
        px = self.render([plane(50, 90, 0, reason="low flyer")], rings_km=[], marker="line")
        x, y = 32 + 15, 32
        self.assertNotEqual(px[(x, y + 3)], tuple(wa.DEFAULT_COLOURS["marker"]))

    def test_crowded_radar_uses_lines(self):
        planes = [plane(20 + i * 5, i * 25, 90) for i in range(13)]
        crowded = self.render(planes, rings_km=[])
        lines = self.render(planes, rings_km=[], marker="line")
        self.assertEqual(crowded, lines)
        self.assertNotEqual(self.render(planes[:12], rings_km=[]), self.render(planes[:12], rings_km=[], marker="line"))


if __name__ == "__main__":
    unittest.main()
