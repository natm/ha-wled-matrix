"""Repeatable pseudo-randomness for animated screens: the same key always gives the same number, so a frame depends
only on the time (and the config's `seed`), with no state between frames."""


def rand(*key):
    """A repeatable pseudo-random number in [0, 1) for `key` (any values; they are joined as text and hashed)."""
    h = 2166136261
    for part in key:
        for ch in str(part):
            h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    return (h ^ (h >> 15)) / 4294967296.0
