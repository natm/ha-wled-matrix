"""Weather and tide screens. Run from the repo root: python3 -m unittest discover tests"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apps", "wled_matrix"))

import wm_tides as wt  # noqa: E402
import wm_weather as ww  # noqa: E402

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 7, 15, 0, tzinfo=UTC)  # Saturday 15:00

FORECAST = [  # a met.no daily forecast as weather.get_forecasts gives it
    {"condition": "partlycloudy", "datetime": "2026-11-07T12:00:00+00:00", "wind_bearing": 130.3,
     "temperature": 11.0, "templow": 3.1, "wind_speed": 9.4, "precipitation": 0},
    {"condition": "rainy", "datetime": "2026-11-08T12:00:00+00:00", "wind_bearing": 129.6,
     "temperature": 10.6, "templow": 2.5, "wind_speed": 23.8, "precipitation": 6.2},
    {"condition": "sunny", "datetime": "2026-11-09T12:00:00+00:00", "temperature": 9, "templow": 2},
]

# Solva (ADMIRALTY 0492A), 7-8 Nov 2026, as UKHO Tides lists them: [UTC time, height m], no high/low given
PREDICTIONS = [["2026-11-06 22:54:00", 1.3], ["2026-11-07 04:48:00", 5.14], ["2026-11-07 11:19:00", 1.24],
               ["2026-11-07 17:06:00", 5.3], ["2026-11-07 23:44:00", 1.12], ["2026-11-08 05:27:00", 5.28],
               ["2026-11-08 12:00:00", 1.13], ["2026-11-08 17:44:00", 5.35]]


def at(px, x, y, w=64):
    return px[y * w + x]


def lit(px, x0, y0, x1, y1, w=64):
    return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1) if sum(at(px, x, y, w)) > 30]


class WeatherValues(unittest.TestCase):
    def test_rounding_is_half_up(self):
        self.assertEqual(ww.r0(2.5), 3)
        self.assertEqual(ww.r0(-2.5), -2)

    def test_rain_text(self):
        self.assertEqual(ww.rain_text(0), "0")
        self.assertEqual(ww.rain_text(0.4), "0.4")
        self.assertEqual(ww.rain_text(6.0), "6")
        self.assertEqual(ww.rain_text(12.4), "12")
        self.assertEqual(ww.rain_text(None), "-")

    def test_wind_conversion(self):
        self.assertAlmostEqual(ww.wind_value(23.8, "km/h", "mph"), 14.79, places=1)
        self.assertAlmostEqual(ww.wind_value(10, "m/s", "kmh"), 36.0)
        self.assertIsNone(ww.wind_value(None))

    def test_temperature_colours_follow_the_scale(self):
        self.assertEqual(ww.temp_colour(-20), ww.TEMP_STOPS[0][1])
        self.assertEqual(ww.temp_colour(40), ww.TEMP_STOPS[-1][1])
        self.assertEqual(ww.temp_colour(10), (120, 220, 40))

    def test_pick_days_starts_today_in_local_time(self):
        days = ww.pick_days(FORECAST, NOW)
        self.assertEqual([d.isoformat() for d, _ in days], ["2026-11-07", "2026-11-08"])
        later = datetime.datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
        self.assertEqual(ww.pick_days(FORECAST, later)[0][0].isoformat(), "2026-11-08")

    def test_animation_still_at_night(self):
        self.assertEqual(ww.animation_phase({}, 1.6, night=True), 0)
        self.assertEqual(ww.animation_phase({"animate": False}, 1.6), 0)
        self.assertEqual(ww.animation_phase({}, 1.6), 0)
        self.assertEqual(ww.animation_phase({}, 1.0), 2)


class WeatherDrawing(unittest.TestCase):
    def test_draws_two_days_with_units_once(self):
        px = ww.render_weather({}, FORECAST, NOW)
        self.assertEqual(len(px), 64 * 64)
        self.assertTrue(lit(px, 0, 9, 31, 27))   # today's icon
        self.assertTrue(lit(px, 33, 9, 63, 27))  # tomorrow's icon
        self.assertTrue(lit(px, 0, 29, 31, 42))  # today's high
        # the units sit in the middle, between the two days' figures, and nowhere else on those rows
        self.assertTrue(lit(px, 29, 52, 35, 56))
        self.assertTrue(lit(px, 27, 58, 37, 62))

    def test_today_is_underlined(self):
        px = ww.render_weather({}, FORECAST, NOW)
        self.assertTrue(lit(px, 0, 7, 31, 7))
        self.assertFalse(lit(px, 33, 7, 63, 7))

    def test_animation_changes_the_icon_only(self):
        a = ww.render_weather({}, FORECAST, NOW, t=0.0)
        b = ww.render_weather({}, FORECAST, NOW, t=0.5)
        changed = [i for i in range(64 * 64) if a[i] != b[i]]
        self.assertTrue(changed)
        self.assertTrue(all(8 <= i // 64 <= 28 for i in changed))  # the icon rows

    def test_no_forecast_says_so(self):
        px = ww.render_weather({}, None, NOW)
        self.assertTrue(lit(px, 0, 26, 63, 36))
        self.assertFalse(lit(px, 0, 0, 63, 20))

    def test_unknown_condition_and_missing_values_do_not_fail(self):
        fc = [{"datetime": "2026-11-07T12:00:00+00:00", "condition": "exceptional"},
              {"datetime": "2026-11-08T12:00:00+00:00", "condition": "lightning-rainy", "temperature": "x"}]
        ww.render_weather({"wind_unit": "kmh"}, fc, NOW)


class TideEvents(unittest.TestCase):
    def test_highs_and_lows_are_inferred(self):
        events = wt.parse_events(PREDICTIONS)
        self.assertEqual("".join(k for _, k, _ in events), "LHLHLHLH")
        self.assertEqual(events[1][0], datetime.datetime(2026, 11, 7, 4, 48, tzinfo=UTC))

    def test_dicts_with_types_and_units(self):
        raw = [{"t": "2026-11-07T17:06:00Z", "h": "5.3m", "kind": "HighWater"},
               {"t": "2026-11-07T11:19:00Z", "h": "1.2 m", "kind": "LowWater"}]
        events = wt.parse_events(raw, {"time_key": "t", "height_key": "h", "type_key": "kind"})
        self.assertEqual([(k, h) for _, k, h in events], [("L", 1.2), ("H", 5.3)])

    def test_bad_items_are_skipped(self):
        self.assertEqual(wt.parse_events([["nonsense", 1], ["2026-11-07 10:00:00", "x"], 5, None]), [])
        self.assertEqual(wt.parse_events(None), [])

    def test_curve_meets_the_events_and_stays_between(self):
        events = wt.parse_events(PREDICTIONS)
        self.assertAlmostEqual(wt.height_at(events, events[3][0]), 5.3)
        mid = events[3][0] + (events[4][0] - events[3][0]) / 2
        self.assertAlmostEqual(wt.height_at(events, mid), (5.3 + 1.12) / 2)
        self.assertIsNone(wt.height_at(events, datetime.datetime(2026, 11, 10, tzinfo=UTC)))

    def test_countdown(self):
        self.assertEqual(wt.countdown(datetime.timedelta(hours=2, minutes=6)), "IN 2H06")


class TideDrawing(unittest.TestCase):
    def test_list_is_the_default_and_fits(self):
        events = wt.parse_events(PREDICTIONS)
        px = wt.render_tides({"label": "NEWGALE"}, events, NOW, UTC)
        self.assertTrue(lit(px, 0, 1, 30, 5))        # place name
        self.assertTrue(lit(px, 60, 1, 62, 5))       # the unit, once
        self.assertTrue(lit(px, 9, 9, 33, 15))       # first time, 17:06
        self.assertTrue(lit(px, 9, 18, 40, 22))      # "IN 2H06"
        self.assertTrue(lit(px, 0, 52, 63, 63))      # fourth tide, after the day divider, still on screen

    def test_curve_layout(self):
        events = wt.parse_events(PREDICTIONS)
        px = wt.render_tides({"label": "NEWGALE", "layout": "curve"}, events, NOW, UTC)
        self.assertTrue(lit(px, 0, 30, 63, 46))      # the sea
        self.assertTrue(lit(px, 0, 50, 63, 62))      # next high and low

    def test_no_events_says_so(self):
        px = wt.render_tides({"label": "NEWGALE"}, [], NOW, UTC)
        self.assertTrue(lit(px, 0, 26, 63, 33))
        self.assertFalse(lit(px, 0, 9, 63, 24))
        old = wt.parse_events(PREDICTIONS[:2])
        self.assertEqual(wt.render_tides({}, old, NOW, UTC), wt.render_tides({}, [], NOW, UTC))


class AppHelpers(unittest.TestCase):
    def test_find_forecast_in_an_appdaemon_reply(self):
        import types
        hassapi = types.ModuleType("appdaemon.plugins.hass.hassapi")
        hassapi.Hass = object
        for name in ("appdaemon", "appdaemon.plugins", "appdaemon.plugins.hass"):
            sys.modules.setdefault(name, types.ModuleType(name))
        sys.modules.setdefault("appdaemon.plugins.hass.hassapi", hassapi)
        import wled_matrix
        reply = {"result": {"response": {"weather.home": {"forecast": FORECAST}}}}
        self.assertEqual(wled_matrix.find_forecast(reply, "weather.home"), FORECAST)
        self.assertIsNone(wled_matrix.find_forecast({"result": {}}, "weather.home"))


if __name__ == "__main__":
    unittest.main()
