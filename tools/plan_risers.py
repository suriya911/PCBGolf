"""Find collision-free spots for the riser groups on all boards they pass through.

Run with KiCad's Python after tools/floorplan.py:
    python tools/plan_risers.py <netlist> <side_mm>

Builds each board with only its anchors, marks the area they block (courtyard
and pads, plus clearance), then puts every riser group on a 2.0 mm grid block
that is free on each board the group's pins touch, as close as possible to the
group's target point. Rewrites placement/risers.json in place.
"""
import json
import math
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
from netlist import load              # noqa: E402
from partition import board_of        # noqa: E402
import risers as R                    # noqa: E402
import place                          # noqa: E402
import build_board                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAR = R.PAD / 2 + 0.15          # pad radius + copper clearance (boxes already carry 0.1 margin)
EDGE = 1.05


def anchor_boxes(netfile, name, spec_file):
    tmp = os.path.join(ROOT, f"_anchors_{name}.kicad_pcb")
    spec = json.load(open(spec_file))
    only = dict(spec)
    json.dump(only, open(tmp + ".json", "w"))
    build_board.build(netfile, name, tmp + ".json", tmp)
    board = pcbnew.LoadBoard(tmp)
    boxes = []
    for fp in board.GetFootprints():
        if fp.GetReference() in spec["parts"]:
            boxes.append(place.courtyard(fp))
    boxes += [tuple(k) for k in spec.get("keepout", [])]
    for f in (tmp, tmp + ".json", tmp.replace(".kicad_pcb", ".kicad_pro")):
        if os.path.exists(f):
            os.remove(f)
    return boxes


def main(netfile, side):
    side = float(side)
    _, nets, _ = load(netfile)
    boards_of = {n: {board_of(r) for r, _, _ in m} for n, m in nets.items()}
    blocked = {b: anchor_boxes(netfile, b, os.path.join(ROOT, "placement", f"{b}.json")) for b in R.ORDER}
    risers = json.load(open(os.path.join(ROOT, "placement", "risers.json")))

    def span(spec):
        if "span" in spec:
            return set(spec["span"])
        out = set()
        for label in spec["nets"]:
            used = sorted(R.ORDER.index(b) for b in boards_of.get(R.net_name(label), ()))
            if used:
                out |= set(R.ORDER[used[0]:used[-1] + 1])
        return out

    def free(x, y, boards):
        if x < EDGE or y < EDGE or x > side - EDGE or y > side - EDGE:
            return False
        for b in boards:
            for (l, t, r, btm) in blocked[b]:
                if l - CLEAR < x < r + CLEAR and t - CLEAR < y < btm + CLEAR:
                    return False
        return True

    # biggest groups first, they are the hardest to fit
    order = sorted(risers, key=lambda k: (-len(span(risers[k])), -len(risers[k]["nets"])))
    for name in order:
        spec = risers[name]
        boards = span(spec)
        tx, ty = spec["at"]
        best = None
        for rows in sorted({spec.get("rows", 1), 1, 2, 3, 4, 7}):
            for d in ("x", "y"):
                trial = dict(spec, rows=rows, dir=d)
                shape = R.pin_positions(dict(trial, at=[0, 0]))
                for gx in range(0, int(side / R.PITCH * 2) + 1):
                    for gy in range(0, int(side / R.PITCH * 2) + 1):
                        x0, y0 = gx * R.PITCH / 2, gy * R.PITCH / 2
                        pins = [(x0 + px, y0 + py) for _, px, py in shape]
                        if not all(free(x, y, boards) for x, y in pins):
                            continue
                        cx = sum(p[0] for p in pins) / len(pins)
                        cy = sum(p[1] for p in pins) / len(pins)
                        # prefer near the target, and compact blocks
                        w = max(p[0] for p in pins) - min(p[0] for p in pins)
                        h = max(p[1] for p in pins) - min(p[1] for p in pins)
                        cost = math.hypot(cx - tx, cy - ty) + 0.3 * (w + h)
                        if best is None or cost < best[0]:
                            best = (cost, x0, y0, rows, d, pins)
        if best is None:
            raise SystemExit(f"{name}: no room on {sorted(boards)}")
        _, x0, y0, rows, d, pins = best
        spec.update({"at": [round(x0, 2), round(y0, 2)], "rows": rows, "dir": d})
        for b in boards:
            for x, y in pins:
                blocked[b].append((x - R.PAD / 2, y - R.PAD / 2, x + R.PAD / 2, y + R.PAD / 2))
        print(f"{name}: {len(pins)} pins on {''.join(sorted(boards))} at ({x0:.1f},{y0:.1f}) {rows} rows dir {d}")
    json.dump(risers, open(os.path.join(ROOT, "placement", "risers.json"), "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
