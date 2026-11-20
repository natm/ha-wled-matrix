"""The clock screen and its styles. Run from the repo root: python3 -m unittest discover tests"""

import datetime
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "apps", "wled_matrix"))

from wm.screens import build  # noqa: E402
from wm.screens.clock import STYLES, ClockScreen, render_clock  # noqa: E402

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 20, 10, 8, 15, 300000, tzinfo=UTC)
LATER = NOW + datetime.timedelta(microseconds=300000)
MOMENTS = [
    NOW,
    datetime.datetime(2026, 11, 20, 10, 8, 59, 850000, tzinfo=UTC),
    datetime.datetime(2026, 11, 20, 21, 47, 0),
]


class FakeHost:
    def __init__(self):
        self.args, self.rng, self.mdi, self.logged = {}, random.Random(0), None, []

    def get_state(self, entity, attribute=None):
        return None

    def log(self, message, **kwargs):
        self.logged.append(message)


def frame_ok(px, n=64 * 64):
    return len(px) == n and all(len(p) == 3 and all(0 <= v <= 255 and isinstance(v, int) for v in p) for p in px)


class Styles(unittest.TestCase):
    def test_the_nine_styles(self):
        self.assertEqual(list(STYLES), ["classic", "minimal", "big", "flip", "sun", "polar", "rain", "bounce", "bars"])

    def test_every_style_draws_a_full_frame(self):
        for key in STYLES:
            for now in MOMENTS:
                for date in (False, True):
                    with self.subTest(style=key, now=now, date=date):
                        px = render_clock({"style": key, "date": date}, now=now, t=1000.0)
                        self.assertTrue(frame_ok(px))
                        self.assertTrue(any(p != (0, 0, 0) for p in px))

    def test_every_style_moves_within_a_second(self):
        for key in STYLES:
            with self.subTest(style=key):
                a = render_clock({"style": key}, now=NOW, t=1000.0)
                b = render_clock({"style": key}, now=LATER, t=1000.3)
                self.assertNotEqual(a, b)

    def test_same_moment_same_frame(self):
        for key in STYLES:
            self.assertEqual(render_clock({"style": key}, now=NOW, t=5.0), render_clock({"style": key}, now=NOW, t=5.0))

    def test_the_date_shows_only_where_a_style_has_room(self):
        for key, module in STYLES.items():
            with self.subTest(style=key):
                on = render_clock({"style": key, "date": True}, now=NOW, t=1.0)
                off = render_clock({"style": key, "date": False}, now=NOW, t=1.0)
                self.assertEqual(on != off, module.DATE)

    def test_other_sizes_get_the_face_centred(self):
        full = render_clock({"style": "classic"}, now=NOW, t=1.0)
        wide = render_clock({"style": "classic"}, 128, 64, now=NOW, t=1.0)
        self.assertTrue(frame_ok(wide, 128 * 64))
        self.assertEqual(wide[20 * 128 + 32 + 10], full[20 * 64 + 10])
        self.assertEqual(wide[20 * 128 + 5], (0, 0, 0))
        self.assertEqual(len(render_clock({"style": "bars"}, 64, 32, now=NOW, t=1.0)), 64 * 32)


class Screen(unittest.TestCase):
    def test_build_and_defaults(self):
        s = build(FakeHost(), "clock", {"clock": {}})
        self.assertIsInstance(s, ClockScreen)
        self.assertEqual(s.frame_rate, 10)  # the second hands sweep without any frame_rate in the config
        self.assertTrue(frame_ok(s.render(64, 64, night=False, t=0.0, now=NOW)))
        self.assertEqual(s.render(64, 64, night=False, t=0.0, now=NOW), render_clock({}, now=NOW, t=0.0))
        self.assertEqual(build(FakeHost(), "c", {"clock": {"style": "polar"}, "frame_rate": 4}).frame_rate, 4)
        self.assertEqual(s.entities(), [])

    def test_unknown_style_fails_at_build_naming_the_screen(self):
        with self.assertRaises(ValueError) as err:
            build(FakeHost(), "hall", {"clock": {"style": "cuckoo"}})
        self.assertIn("hall", str(err.exception))
        self.assertIn("classic", str(err.exception))

    def test_without_a_time_it_uses_the_system_clock(self):
        s = build(FakeHost(), "clock", {"clock": {"style": "big"}})
        self.assertTrue(frame_ok(s.render(64, 64, night=False, t=0.0, now=None)))


if __name__ == "__main__":
    unittest.main()
