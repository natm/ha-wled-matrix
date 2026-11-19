"""Entity states as numbers, and how a value is shown: number text, unit, colour and icon by thresholds."""

ON_STATES = {"on", "open", "home", "heat", "heating", "true", "detected", "playing"}
OFF_STATES = {"off", "closed", "not_home", "idle", "false", "clear", "paused", "standby"}


def to_number(state, fmt="number"):
    """An entity state as a number: on/off states become 1/0, numbers parse, anything else is None."""
    if state is None:
        return None
    if isinstance(state, (int, float)):
        return float(state)
    s = str(state).strip().lower()
    if fmt == "onoff":
        return 1.0 if s in ON_STATES else 0.0 if s in OFF_STATES else None
    try:
        return float(s)
    except ValueError:
        return None


def format_value(value, fmt):
    """Return (number text, unit text) for a row."""
    if value is None:
        return "-", ""
    if fmt == "onoff":
        return ("on" if value >= 1 else "off"), ""
    if fmt == "percent":
        return str(int(round(max(0, min(100, value))))), "%"
    if fmt == "power":  # watts in, W or kW out
        w = int(round(value))
        if abs(w) >= 1000:
            return f"{w / 1000:.1f}", "kW"
        return str(w), "W"
    if fmt == "mbps":  # Mbit/s in: 1 decimal below 10, whole numbers to 999, then Gbit/s
        if abs(value) >= 1000:
            return f"{value / 1000:.1f}", "G"
        if abs(value) < 10:
            return f"{value:.1f}", "M"
        return str(int(round(value))), "M"
    if fmt == "clock":  # minutes after midnight in, H:MM out (e.g. 402 -> 6:42)
        m = int(round(value)) % 1440
        return f"{m // 60}:{m % 60:02d}", ""
    if fmt == "number":
        return str(int(round(value))), ""
    if fmt.startswith("decimal"):  # e.g. decimal1
        return f"{value:.{int(fmt[7:] or 1)}f}", ""
    return str(value), ""


def pick_colour(value, row):
    """A row's colour: fixed `colour`, or the first `thresholds` entry whose `above` the value exceeds."""
    for t in row.get("thresholds", []):
        if value is not None and value >= t["above"]:
            return tuple(t["colour"])
    return tuple(row.get("colour", (200, 200, 200)))


def pick_icon(value, row):
    """A row's icon: the first `icon_thresholds` entry whose `above` the value reaches, else `icon`."""
    for t in row.get("icon_thresholds", []):
        if value is not None and value >= t["above"]:
            return t["icon"]
    return row["icon"]
