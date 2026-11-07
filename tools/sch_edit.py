"""Generic schematic surgery used by the part-swap scripts.

The idea: remove a symbol together with the wire stubs that only served it,
then re-attach every net to the replacement symbol with a short stub and a
label (or power symbol). Nets that only had an anonymous wire to the old pin
get a readable local label on both sides.
"""
import copy
import math
import uuid as uuidlib

from sexpr import Q, find, first, value
from schgeom import lib_pins, pin_tip, place

GRID = 2.54


def new_uuid():
    return Q(str(uuidlib.uuid4()))


def pt(xy):
    return (round(float(xy[0]), 3), round(float(xy[1]), 3))


class Sheet:
    def __init__(self, root):
        self.root = root
        self.libs = {s[1]: s for s in find(first(root, "lib_symbols"), "symbol")}

    # ---- queries -------------------------------------------------------
    def symbols(self):
        return find(self.root, "symbol")

    def ref(self, sym):
        for p in find(sym, "property"):
            if p[1] == "Reference":
                return p[2]

    def by_ref(self, ref):
        return [s for s in self.symbols() if self.ref(s) == ref][0]

    def wires(self):
        out = []
        for w in find(self.root, "wire"):
            p = first(w, "pts")
            out.append((pt(p[1][1:3]), pt(p[2][1:3]), w))
        return out

    def label_nodes(self):
        out = []
        for kind in ("label", "global_label", "hierarchical_label"):
            for lab in find(self.root, kind):
                out.append((pt(first(lab, "at")[1:3]), lab))
        return out

    def symbol_tips(self, exclude=()):
        tips = {}
        for s in self.symbols():
            if s in exclude:
                continue
            for num, pts in pin_tip(s, self.libs[value(s, "lib_id")]).items():
                for p in pts:
                    tips.setdefault(p, []).append((s, num))
        return tips

    def points_used(self, exclude_wire=None):
        """Every connection point that isn't the given wire."""
        used = {}
        for a, b, w in self.wires():
            if w is exclude_wire:
                continue
            used.setdefault(a, []).append(w)
            used.setdefault(b, []).append(w)
        return used

    # ---- edits ---------------------------------------------------------
    def remove(self, node):
        self.root.remove(node)

    def cleanup(self, protect=()):
        """Iteratively drop dangling wires, orphan labels, power flags, junctions, NC flags."""
        changed = True
        while changed:
            changed = False
            tips = self.symbol_tips()
            sig_tips = {p for p, owners in tips.items()
                        if any(not self.is_power(s) for s, _ in owners)}
            labels = {p for p, _ in self.label_nodes()}
            wires = self.wires()
            ends = {}
            for a, b, w in wires:
                ends.setdefault(a, 0)
                ends.setdefault(b, 0)
                ends[a] += 1
                ends[b] += 1
            junctions = {pt(first(j, "at")[1:3]): j for j in find(self.root, "junction")}

            def mid_hits(p):
                # a wire end can also land in the middle of another wire
                for a, b, w in wires:
                    if p in (a, b):
                        continue
                    if min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and \
                       min(a[1], b[1]) <= p[1] <= max(a[1], b[1]) and \
                       (a[0] == b[0] == p[0] or a[1] == b[1] == p[1]):
                        return True
                return False

            for a, b, w in wires:
                for end in (a, b):
                    attached = (ends[end] > 1 or end in tips or end in labels
                                or end in protect or mid_hits(end))
                    if not attached:
                        self.remove(w)
                        changed = True
                        break
                if changed:
                    break
            if changed:
                continue
            wire_pts = set(ends)
            for p, lab in self.label_nodes():
                if p not in wire_pts and p not in sig_tips and p not in protect:
                    self.remove(lab)
                    changed = True
            for s in self.symbols():
                if self.is_power(s):
                    ps = [p for pts in pin_tip(s, self.libs[value(s, "lib_id")]).values() for p in pts]
                    if not any(p in wire_pts or p in sig_tips for p in ps):
                        self.remove(s)
                        changed = True
            for p, j in junctions.items():
                if ends.get(p, 0) + (1 if mid_hits(p) else 0) < 3:
                    self.remove(j)
                    changed = True
            for nc in find(self.root, "no_connect"):
                p = pt(first(nc, "at")[1:3])
                if p not in tips:
                    self.remove(nc)
                    changed = True

    def is_power(self, sym):
        lib = self.libs.get(value(sym, "lib_id"))
        return lib is not None and first(lib, "power") is not None

    def add_wire(self, a, b):
        node = [
            "wire",
            ["pts", ["xy", f"{a[0]:g}", f"{a[1]:g}"], ["xy", f"{b[0]:g}", f"{b[1]:g}"]],
            ["stroke", ["width", "0"], ["type", "default"]],
            ["uuid", new_uuid()],
        ]
        self.root.append(node)

    def add_label(self, template, text, at, angle):
        node = copy.deepcopy(template)
        node[1] = Q(text)
        a = first(node, "at")
        a[1:] = [f"{at[0]:g}", f"{at[1]:g}", f"{angle:g}"]
        eff = first(node, "effects")
        j = first(eff, "justify")
        just = "left" if angle in (0, 90) else "right"
        if j is None:
            eff.append(["justify", just])
        else:
            j[1:] = [just]
        u = first(node, "uuid")
        u[1] = new_uuid()
        for prop in find(node, "property"):
            pa = first(prop, "at")
            if pa is not None:
                pa[1:4] = [f"{at[0]:g}", f"{at[1]:g}", "0"]
        self.root.append(node)

    def add_no_connect(self, at):
        self.root.append(["no_connect", ["at", f"{at[0]:g}", f"{at[1]:g}"], ["uuid", new_uuid()]])

    def add_power(self, template, at, angle, ref):
        node = copy.deepcopy(template)
        a = first(node, "at")
        a[1:] = [f"{at[0]:g}", f"{at[1]:g}", f"{angle:g}"]
        first(node, "uuid")[1] = new_uuid()
        for p in find(node, "property"):
            pa = first(p, "at")
            if pa is not None:
                pa[1:3] = [f"{at[0]:g}", f"{at[1]:g}"]
            if p[1] == "Reference":
                p[2] = Q(ref)
        for pin in find(node, "pin"):
            first(pin, "uuid")[1] = new_uuid()
        for inst in find(node, "instances"):
            for proj in find(inst, "project"):
                for path in find(proj, "path"):
                    r = first(path, "reference")
                    if r is not None:
                        r[1] = Q(ref)
        # power symbols don't always have their pin at the origin; shift so it lands on `at`
        tip = list(pin_tip(node, self.libs[value(node, "lib_id")]).values())[0][0]
        dx, dy = at[0] - tip[0], at[1] - tip[1]
        if dx or dy:
            a[1:3] = [f"{at[0] + dx:g}", f"{at[1] + dy:g}"]
            for p in find(node, "property"):
                pa = first(p, "at")
                if pa is not None:
                    pa[1:3] = [f"{float(pa[1]) + dx:g}", f"{float(pa[2]) + dy:g}"]
        self.root.append(node)


def pin_outward(pin_rot):
    """Unit vector pointing away from the symbol body for a pin with this lib rotation."""
    # lib pin rotation is the direction from the tip into the body (y up)
    a = math.radians(pin_rot)
    dx, dy = math.cos(a), -math.sin(a)  # into the body, sheet coords
    return (-round(dx), -round(dy))


def label_angle(out):
    return {(-1, 0): 180, (1, 0): 0, (0, -1): 90, (0, 1): 270}[out]


def _shift_at(node, dx, dy):
    a = first(node, "at")
    if a is not None:
        a[1:3] = [f"{float(a[1]) + dx:g}", f"{float(a[2]) + dy:g}"]
    for p in find(node, "property"):
        _shift_at(p, dx, dy)


def move_group(sheet, refs, dx, dy):
    """Move symbols plus every wire/label/junction hanging off their pins (not other symbols)."""
    syms = [sheet.by_ref(r) for r in refs]
    frontier = set()
    for s in syms:
        for pts in pin_tip(s, sheet.libs[value(s, "lib_id")]).values():
            frontier.update(pts)
    other_tips = sheet.symbol_tips(exclude=syms)
    seen_pts, wires = set(), []
    while frontier:
        p = frontier.pop()
        if p in seen_pts:
            continue
        seen_pts.add(p)
        if p in other_tips and not all(sheet.is_power(s) for s, _ in other_tips[p]):
            continue  # stop at foreign pins
        for a, b, w in sheet.wires():
            if p in (a, b) and w not in wires:
                wires.append(w)
                frontier.add(b if p == a else a)
    for s in syms:
        _shift_at(s, dx, dy)
    for w in wires:
        for xy in find(first(w, "pts"), "xy"):
            xy[1:3] = [f"{float(xy[1]) + dx:g}", f"{float(xy[2]) + dy:g}"]
    for p, lab in sheet.label_nodes():
        if p in seen_pts:
            _shift_at(lab, dx, dy)
    for j in find(sheet.root, "junction"):
        if pt(first(j, "at")[1:3]) in seen_pts:
            _shift_at(j, dx, dy)
    for s in sheet.symbols():
        if sheet.is_power(s) and s not in syms:
            tips = [q for pts in pin_tip(s, sheet.libs[value(s, "lib_id")]).values() for q in pts]
            if any(q in seen_pts for q in tips):
                _shift_at(s, dx, dy)
