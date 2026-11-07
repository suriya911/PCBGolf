"""Greedy placer: hand-placed anchors, everything else packed next to what it connects to.

Run with KiCad's Python:
    python tools/place.py <board.kicad_pcb> <placement.json> [--write placement.json]

placement.json: {"outline": [w, h],
                 "parts": {"U3": [x, y, rot], ...},          # anchors, never moved
                 "keepout": [[x1, y1, x2, y2], ...]}          # nothing may be placed here

For each free part the target is the weighted centroid of the pads it shares
a net with on already-placed parts. Big nets (GND, rails) get a tiny weight so
a decoupling cap goes to the IC pin it decouples rather than to the middle of
the board. Parts are placed most-connected first; each one goes to the free
spot nearest its target (spiral search), trying 0/90 degrees. Placed parts
become attractors for the parts that follow, so small clusters (LED + its
resistor) form on their own.
"""
import json
import math
import sys
from collections import defaultdict

import pcbnew

GAP = 0.35        # courtyard to courtyard: leaves channels for traces and 0R jumpers
STEP = 0.1        # search grid
EDGE = 0.25       # copper/courtyard keep-in from the board edge


def mm(v):
    return pcbnew.FromMM(v)


def to_mm(v):
    return pcbnew.ToMM(v)


def courtyard(fp):
    """Courtyard bbox in mm, grown to cover every pad (some vendor footprints draw the
    courtyard around the body only and leave the pads outside it)."""
    boxes = []
    try:
        poly = fp.GetCourtyard(pcbnew.F_CrtYd)
        if poly.OutlineCount():
            bb = poly.BBox()
            boxes.append((bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))
    except Exception:
        pass
    for pad in fp.Pads():
        bb = pad.GetBoundingBox()
        m = pcbnew.FromMM(0.1)
        boxes.append((bb.GetLeft() - m, bb.GetTop() - m, bb.GetRight() + m, bb.GetBottom() + m))
    if not boxes:
        bb = fp.GetBoundingBox(False)
        boxes.append((bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))
    l, t, r, b = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                  max(b[2] for b in boxes), max(b[3] for b in boxes))
    return to_mm(l), to_mm(t), to_mm(r), to_mm(b)


def overlaps(a, b, gap=GAP):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def main(pcb, placement, write=None):
    spec = json.load(open(placement))
    w, h = spec["outline"]
    anchors = spec.get("parts", {})
    keepout = [tuple(k) for k in spec.get("keepout", [])]

    board = pcbnew.LoadBoard(pcb)
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}

    net_size = defaultdict(int)
    for fp in fps.values():
        for pad in fp.Pads():
            if pad.GetNetname():
                net_size[pad.GetNetname()] += 1

    placed = {}
    for ref, fp in fps.items():
        if fp.GetValue() == "riser":          # risers come from risers.json, never moved
            placed[ref] = courtyard(fp)
    for ref, (x, y, rot) in anchors.items():
        if ref in fps:
            fps[ref].SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
            fps[ref].SetOrientationDegrees(rot)
            placed[ref] = courtyard(fps[ref])

    def pad_xy(pad):
        p = pad.GetPosition()
        return to_mm(p.x), to_mm(p.y)

    def target(fp):
        sx = sy = sw = 0.0
        for pad in fp.Pads():
            net = pad.GetNetname()
            if not net:
                continue
            wgt = 1.0 / max(1, net_size[net] - 1) ** 1.5
            for ref, other in fps.items():
                if ref not in placed or ref == fp.GetReference():
                    continue
                for op in other.Pads():
                    if op.GetNetname() == net:
                        x, y = pad_xy(op)
                        sx += wgt * x
                        sy += wgt * y
                        sw += wgt
        if sw == 0:
            return None, 0.0
        return (sx / sw, sy / sw), sw

    def legal(box):
        if box[0] < EDGE or box[1] < EDGE or box[2] > w - EDGE or box[3] > h - EDGE:
            return False
        if any(overlaps(box, k, 0) for k in keepout):
            return False
        return not any(overlaps(box, b) for b in placed.values())

    todo = [r for r in fps if r not in placed]
    unplaced = []
    while todo:
        # most strongly connected to what is already down goes next
        scored = [(target(fps[r])[1], r) for r in todo]
        scored.sort(reverse=True)
        _, ref = scored[0]
        fp = fps[ref]
        tgt, _ = target(fp)
        if tgt is None:
            tgt = (w / 2, h / 2)
        best = None
        for rot in (0, 90):
            fp.SetOrientationDegrees(rot)
            fp.SetPosition(pcbnew.VECTOR2I(mm(tgt[0]), mm(tgt[1])))
            c = courtyard(fp)
            ox, oy = tgt[0] - (c[0] + c[2]) / 2, tgt[1] - (c[1] + c[3]) / 2  # origin vs box centre
            hw, hh = (c[2] - c[0]) / 2, (c[3] - c[1]) / 2
            radius = 0.0
            found = None
            while radius < max(w, h) and found is None:
                n = max(1, int(2 * math.pi * radius / STEP))
                for i in range(n):
                    a = 2 * math.pi * i / n
                    cx, cy = tgt[0] + radius * math.cos(a), tgt[1] + radius * math.sin(a)
                    box = (cx - hw, cy - hh, cx + hw, cy + hh)
                    if legal(box):
                        found = (radius, cx + ox, cy + oy, box)
                        break
                radius += STEP
            if found and (best is None or found[0] < best[0] - 1e-6):
                best = (found[0], rot, found[1], found[2], found[3])
        todo.remove(ref)
        if best is None:
            unplaced.append(ref)
            continue
        _, rot, x, y, box = best
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        placed[ref] = courtyard(fp)

    board.Save(pcb)
    print(f"placed {len(placed)} parts, could not place: {unplaced or 'none'}")
    if write:
        out = dict(spec)
        out["parts"] = {}
        for ref, fp in fps.items():
            p = fp.GetPosition()
            out["parts"][ref] = [round(to_mm(p.x), 3), round(to_mm(p.y), 3), fp.GetOrientationDegrees()]
        out["anchors"] = sorted(anchors)
        json.dump(out, open(write, "w"), indent=1)


if __name__ == "__main__":
    args = sys.argv[1:]
    write = None
    if "--write" in args:
        i = args.index("--write")
        write = args[i + 1]
        del args[i:i + 2]
    main(args[0], args[1], write)
