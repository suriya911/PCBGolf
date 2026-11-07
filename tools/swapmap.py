"""Pin translation used by netcheck.py for all the part swaps in this design.

Both netlists are mapped onto a common key per pin. For the MCU the key is the
pin *name* after remapping (power pins repeat, so they collapse to one key).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from mcu_pinmap import REMAP, DROPPED  # noqa: E402

# parts removed on purpose (their function is gone with the old package)
DROP = set(DROPPED.values())

# supply pins that only exist on the bigger package
POWER_ALIAS = {"VDD50USB": "VDD33USB"}

_names = {}


def _pin_names(ctx, side):
    if side not in _names:
        _names[side] = ctx["by_name"](ctx[side], "U3")
    return _names[side]


def translate(ref, pin, ctx, side):
    if ref != "U3":
        return (ref, pin)
    name = _pin_names(ctx, side).get(pin)
    if side == "orig":
        if name in DROPPED:
            return None
        name = REMAP.get(name, name)
    name = POWER_ALIAS.get(name, name)
    return ("U3", name)
