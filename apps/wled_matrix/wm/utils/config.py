"""Config values drawn at random.

Anywhere in a screen's config, `{random: [low, high]}` stands for a whole number from `low` to `high` inclusive, drawn
again each time the screen comes up on a matrix (see `Screen.on_show`). It works at any depth, for a screen's own
options (`fish: {random: [1, 10]}`) and for the generic ones (`dwell: {random: [10, 20]}`).
"""

import random


def resolve(value, rng=random, path="screen"):
    """`value` with every `{random: [low, high]}` replaced by a number from `rng`, recursively; anything else is copied.

    `path` names where we are in the config, for the error when a placeholder is malformed.
    """
    if isinstance(value, dict):
        if set(value) == {"random"}:
            return _whole_number(value["random"], rng, path)
        return {k: resolve(v, rng, f"{path}.{k}") for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, rng, f"{path}[{i}]") for i, v in enumerate(value)]
    return value


def _whole_number(bounds, rng, path):
    try:
        low, high = bounds
        if not all(float(b).is_integer() for b in (low, high)) or low > high:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError(
            f"{path}: random needs [low, high], two whole numbers with low <= high, not {bounds!r}"
        ) from None
    return rng.randint(int(low), int(high))
