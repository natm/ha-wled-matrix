"""`{random: [low, high]}` config values. Run from the repo root: python3 -m unittest discover tests"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "apps", "wled_matrix"))

from wm.utils.config import resolve  # noqa: E402


class Resolve(unittest.TestCase):
    def test_plain_values_come_back_unchanged(self):
        cfg = {"fish": 7, "seed": 0, "colours": [[1, 2, 3]], "name": "x", "flag": True, "nothing": None}
        self.assertEqual(resolve(cfg, random.Random(1)), cfg)

    def test_a_placeholder_becomes_a_whole_number_in_range_inclusive(self):
        rng = random.Random(0)
        seen = {resolve({"random": [1, 3]}, rng) for _ in range(200)}
        self.assertEqual(seen, {1, 2, 3})

    def test_placeholders_anywhere_in_the_tree(self):
        cfg = {
            "aquarium": {"fish": {"random": [1, 10]}, "kids": [{"n": {"random": [5, 5]}}]},
            "dwell": {"random": [10, 20]},
        }
        out = resolve(cfg, random.Random(0))
        self.assertTrue(1 <= out["aquarium"]["fish"] <= 10)
        self.assertEqual(out["aquarium"]["kids"][0]["n"], 5)
        self.assertTrue(10 <= out["dwell"] <= 20)
        self.assertEqual(cfg["aquarium"]["fish"], {"random": [1, 10]})  # the input is untouched

    def test_a_dict_with_more_than_the_random_key_is_not_a_placeholder(self):
        cfg = {"random": [1, 2], "other": 3}
        self.assertEqual(resolve(cfg, random.Random(0)), cfg)

    def test_bad_bounds_name_the_key(self):
        for bad in ([1], [1, 2, 3], [1.5, 2], ["a", "b"], [10, 1], 7):
            with self.assertRaises(ValueError) as err:
                resolve({"aquarium": {"fish": {"random": bad}}}, random.Random(0), "tank")
            self.assertIn("tank.aquarium.fish", str(err.exception))

    def test_whole_floats_are_accepted(self):
        self.assertEqual(resolve({"random": [2.0, 2.0]}, random.Random(0)), 2)


if __name__ == "__main__":
    unittest.main()
