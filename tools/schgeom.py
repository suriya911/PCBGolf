"""Schematic geometry helpers: where symbol pins land on the sheet and what touches them."""
import math

from sexpr import find, first, value


def lib_pins(lib_symbol):
    """All pins of a lib symbol (any unit/body style) -> list of dicts."""
    out = []

    def walk(node):
        for c in node[1:]:
            if not isinstance(c, list) or not c:
                continue
            if c[0] == "pin":
                at = first(c, "at")
                out.append({
                    "etype": c[1],
                    "number": value(c, "number"),
                    "name": value(c, "name"),
                    "x": float(at[1]),
                    "y": float(at[2]),
                    "rot": float(at[3]) if len(at) > 3 else 0.0,
                    "length": float(value(c, "length", 0)),
                })
            else:
                walk(c)

    walk(lib_symbol)
    return out


def place(inst_at, mirror, px, py):
    """Library coords (y up) -> sheet coords (y down) for a placed symbol."""
    x0, y0 = float(inst_at[1]), float(inst_at[2])
    rot = float(inst_at[3]) if len(inst_at) > 3 else 0.0
    y = -py
    x = px
    if mirror == "x":
        y = -y
    elif mirror == "y":
        x = -x
    a = math.radians(-rot)
    xr = x * math.cos(a) - y * math.sin(a)
    yr = x * math.sin(a) + y * math.cos(a)
    return round(x0 + xr, 3), round(y0 + yr, 3)


def pin_tip(inst, lib_symbol):
    """Pin number -> (x, y) of the electrical connection point on the sheet."""
    at = first(inst, "at")
    mirror = value(inst, "mirror")
    tips = {}
    for p in lib_pins(lib_symbol):
        tips.setdefault(p["number"], []).append(place(at, mirror, p["x"], p["y"]))
    return tips


def wires(sheet):
    out = []
    for w in find(sheet, "wire"):
        pts = first(w, "pts")
        xy = [(round(float(p[1]), 3), round(float(p[2]), 3)) for p in pts[1:]]
        out.append((xy[0], xy[1], w))
    return out


def labels(sheet):
    out = []
    for kind in ("label", "global_label", "hierarchical_label"):
        for lab in find(sheet, kind):
            at = first(lab, "at")
            out.append((kind, lab[1], (round(float(at[1]), 3), round(float(at[2]), 3)), lab))
    return out
