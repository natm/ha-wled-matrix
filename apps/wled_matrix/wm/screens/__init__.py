"""Screen types: one module per kind of screen, each with a `Screen` subclass (see base.py).

Importing a module here is what registers its type: to add a screen, add its module and one line below.
"""

from . import aircraft, camera, clock, fun, items, network, power, stars, tides, weather
from .base import Screen, build

__all__ = [
    "Screen",
    "build",
    "aircraft",
    "camera",
    "clock",
    "fun",
    "items",
    "network",
    "power",
    "stars",
    "tides",
    "weather",
]
