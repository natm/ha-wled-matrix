"""Rotation with pins, and the sensor per matrix. Run from the repo root: python3 -m unittest discover tests"""

import os
import random
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apps", "wled_matrix"))

from wm.screens import build  # noqa: E402

hassapi = types.ModuleType("appdaemon.plugins.hass.hassapi")
hassapi.Hass = object
for name in ("appdaemon", "appdaemon.plugins", "appdaemon.plugins.hass"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules.setdefault("appdaemon.plugins.hass.hassapi", hassapi)
import wled_matrix  # noqa: E402

SCREENS = {"energy": {"rows": []}, "radar": {"aquarium": {}}, "weather": {"jungle": {}}, "tides": {"blocks": {}}}


def app(matrices=None, states=None):
    """A WledMatrix with the pieces initialize() would set up, no AppDaemon: get_state, set_state and call_service
    are recorded in place."""
    a = wled_matrix.WledMatrix()
    a.screens = SCREENS
    a.matrices = matrices or [{"host": "a", "name": "Kitchen", "screens": ["energy", "radar", "weather"], "dwell": 10}]
    a.refresh = 1.0
    a.rng, a.args = random.Random(0), {}
    a.screen_objects = {n: build(a, n, s) for n, s in a.screens.items()}
    a.position = {m["host"]: 0 for m in a.matrices}
    a.elapsed = {m["host"]: 0.0 for m in a.matrices}
    a.interrupt, a.restart_sig, a.pinned, a.published, a.selects, a.showing = {}, {}, {}, {}, {}, {}
    a.states = states or {}
    a.get_state = lambda e, **kw: a.states.get(e)
    a.set_states, a.calls, a.logged = [], [], []
    a.set_state = lambda e, state=None, attributes=None: a.set_states.append((e, state, attributes))
    a.call_service = lambda name, **data: a.calls.append((name, data))
    a.log = lambda msg, **kw: a.logged.append(msg)
    a.listen_state = lambda cb, entity: a.calls.append(("listen", {"entity": entity}))
    return a


class Pins(unittest.TestCase):
    def test_a_pin_beats_the_rotation_and_any_screen_can_be_pinned(self):
        a = app()
        m = a.matrices[0]
        self.assertEqual(a.choose(m), "energy")
        a.pin("a", "tides")  # not in this matrix's rotation
        self.assertEqual(a.choose(m), "tides")
        self.assertEqual(a.choose(m), "tides")
        a.pin("a", None)
        self.assertEqual(a.choose(m), "energy")

    def test_unknown_screens_are_refused(self):
        with self.assertRaises(ValueError):
            app().pin("a", "nope")

    def test_pinning_sets_the_matrix_select(self):
        a = app([{"host": "a", "screens": ["energy"], "select_entity": "input_select.k"}])
        a.pin("a", "radar")
        self.assertEqual(
            a.calls[-1], ("input_select/select_option", {"entity_id": "input_select.k", "option": "radar"})
        )
        a.pin("a", None)
        self.assertEqual(a.calls[-1][1]["option"], wled_matrix.AUTO)
        a.pin("a", "radar", sync=False)
        self.assertEqual(len(a.calls), 2)

    def test_the_select_pins_the_matrix(self):
        a = app(
            [{"host": "a", "screens": ["energy"], "select_entity": "input_select.k"}], {"input_select.k": "weather"}
        )
        a.setup_select(a.matrices[0])
        self.assertEqual(a.calls[0][0], "input_select/set_options")
        self.assertEqual(a.calls[0][1]["options"], ["Auto", "energy", "radar", "tides", "weather"])
        self.assertEqual(a.pinned, {"a": "weather"})  # the helper's current option applies at start-up
        a.on_select("input_select.k", "state", "weather", "radar")
        self.assertEqual(a.pinned, {"a": "radar"})
        self.assertEqual(len([c for c in a.calls if c[0] == "input_select/select_option"]), 0)  # no echo back
        a.on_select("input_select.k", "state", "radar", "Auto")
        self.assertEqual(a.pinned, {})


class NextAndRemaining(unittest.TestCase):
    def test_next_screen_and_time_left(self):
        a = app()
        m = a.matrices[0]
        a.choose(m)
        self.assertEqual(a.next_screen(m), "radar")
        self.assertEqual(a.remaining(m), 9.0)
        for _ in range(9):
            a.choose(m)
        self.assertEqual(a.choose(m), "radar")
        self.assertEqual(a.next_screen(m), "weather")
        a.pin("a", "energy")
        self.assertIsNone(a.next_screen(m))
        self.assertEqual(a.remaining(m), 0.0)

    def test_status_for_the_live_view(self):
        a = app()
        a.choose(a.matrices[0])
        status = a.matrix_status(a.matrices[0])
        self.assertEqual(status["next"], "radar")
        self.assertEqual(status["dwell"], 10)
        self.assertEqual(status["sensor"], "sensor.wled_matrix_kitchen")
        self.assertTrue(status["enabled"])
        self.assertIsNone(status["pinned"])


class Sensor(unittest.TestCase):
    def test_entity_names(self):
        self.assertEqual(
            wled_matrix.state_entity({"host": "10.0.0.5", "name": "Kitchen Panel"}), "sensor.wled_matrix_kitchen_panel"
        )
        self.assertEqual(wled_matrix.state_entity({"host": "10.0.0.5"}), "sensor.wled_matrix_10_0_0_5")
        self.assertEqual(wled_matrix.state_entity({"host": "x", "state_entity": "sensor.mine"}), "sensor.mine")

    def test_state_and_attributes(self):
        m = {"host": "h", "name": "Hall", "screens": ["a", "b"]}
        self.assertEqual(wled_matrix.matrix_state(m, "a", None, "b", True)[0], "a")
        self.assertEqual(wled_matrix.matrix_state(m, None, None, None, True)[0], "idle")
        self.assertEqual(wled_matrix.matrix_state(m, None, None, None, False)[0], "off")
        attrs = wled_matrix.matrix_state(m, "a", "a", None, True)[1]
        self.assertEqual(attrs["friendly_name"], "Hall")
        self.assertEqual(attrs["screens"], ["a", "b"])
        self.assertEqual(attrs["pinned"], "a")

    def test_written_only_when_something_changes(self):
        a = app()
        a.draw = lambda m, name, night: None
        a.is_night = lambda: False
        a.tick({})
        a.tick({})
        self.assertEqual(len(a.set_states), 1)
        entity, state, attrs = a.set_states[0]
        self.assertEqual((entity, state, attrs["next"]), ("sensor.wled_matrix_kitchen", "energy", "radar"))
        a.pin("a", "weather")
        a.tick({})
        self.assertEqual(a.set_states[-1][1], "weather")
        self.assertEqual(a.set_states[-1][2]["pinned"], "weather")

    def test_off_when_the_switch_is_off(self):
        a = app([{"host": "a", "screens": ["energy"], "enabled_entity": "input_boolean.x"}], {"input_boolean.x": "off"})
        a.draw = lambda m, name, night: None
        a.is_night = lambda: False
        a.tick({})
        self.assertEqual(a.set_states[-1][1], "off")
        self.assertEqual(a.showing, {})


if __name__ == "__main__":
    unittest.main()
