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

# --- USB hub: USB2517 -> 2x CH334R --------------------------------------
# Everything that belonged to the old hub (or the new ones) is left out of the
# 1:1 comparison; the new hub wiring is checked explicitly in extra_checks().
DROP |= {"U4", "U17", "Y2", "Y3", "C28", "C32", "C33", "C34", "C35", "C36",
         "R24", "R25", "R26", "R27", "R28", "R29", "R30"}

HUB_EXPECT = [
    # (net members that must share one net)
    {("J3", "A6"), ("U4", "11")}, {("J3", "A7"), ("U4", "10")},
    {("U4", "8"), ("J5", "A6")}, {("U4", "7"), ("J5", "A7")},
    {("U4", "6"), ("J6", "A6")}, {("U4", "5"), ("J6", "A7")},
    {("U4", "4"), ("J7", "A6")}, {("U4", "3"), ("J7", "A7")},
    {("U4", "2"), ("U17", "11")}, {("U4", "1"), ("U17", "10")},
    {("U17", "8"), ("J8", "A6")}, {("U17", "7"), ("J8", "A7")},
    {("U17", "6"), ("U3", "PA12")}, {("U17", "5"), ("U3", "PA11")},
    {("U4", "16"), ("Y2", "1")}, {("U4", "15"), ("Y2", "3")},
    {("U17", "16"), ("Y3", "1")}, {("U17", "15"), ("Y3", "3")},
    {("U4", "12"), ("U4", "13"), ("U17", "12"), ("U17", "13"), ("U3", "VDD")},
    {("U4", "14"), ("U17", "14"), ("U3", "VSS")},
]


def extra_checks(nets, ctx):
    errors = []
    where = {}
    for name, members in nets.items():
        for r, p, _ in members:
            key = translate(r, p, ctx, "new")
            if key:
                where[key] = name
    for group in HUB_EXPECT:
        found = {where.get(k) for k in group}
        if len(found) != 1 or None in found:
            errors.append(f"hub wiring: {sorted(group)} -> {found}")
    return errors

# --- passive clean-up (tools/shrink_passives.py) --------------------------
# parallel duplicates and DNP parts are dropped; 0R links merge their two nets
DROP |= {"C6", "C10", "R5", "R6", "R32", "R45"}
SHORTED = {"R38", "R39", "R40", "R41", "R42", "R43"}

# --- OPA197 SOIC-8 -> SOT-23-5 --------------------------------------------
OPAMP_PINS = {"6": "1", "4": "2", "3": "3", "2": "4", "7": "5"}
OPAMPS = {"U9", "U10", "U11", "U12"}
_translate_base = translate


def translate(ref, pin, ctx, side):  # noqa: F811
    if ref in OPAMPS and side == "orig":
        return (ref, OPAMP_PINS[pin]) if pin in OPAMP_PINS else None
    return _translate_base(ref, pin, ctx, side)

# DNP in the original design, now kept off the board entirely
DROP |= {"J4", "BH1", "BH2", "BH3", "BH4"}

# --- USB-C receptacles -> stock USB_C_Receptacle symbol --------------------
USB_REFS = {"J3", "J5", "J6", "J7", "J8"}
_translate_usb_base = translate


def translate(ref, pin, ctx, side):  # noqa: F811
    if ref in USB_REFS:
        if pin.startswith("S"):
            return (ref, "SH")
        return (ref, pin[:-1] if pin.endswith("T") else pin)
    return _translate_usb_base(ref, pin, ctx, side)
