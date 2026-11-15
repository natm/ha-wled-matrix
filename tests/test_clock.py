import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "wled_matrix"))

from wm_glyphs import BIG  # noqa: E402
from wm_render import format_value, render_screen  # noqa: E402


def test_clock_format():
    assert format_value(402, "clock") == ("6:42", "")
    assert format_value(0, "clock") == ("0:00", "")
    assert format_value(1439, "clock") == ("23:59", "")
    assert format_value(None, "clock") == ("-", "")


def test_colon_glyph_is_seven_rows():
    assert len(BIG[":"]) == 7


def test_clock_renders():
    screen = {"rows": [{"entity": "sensor.x", "format": "clock"}]}
    px = render_screen(screen, ["402"], 64, 64)
    assert any(any(p) for p in px)
