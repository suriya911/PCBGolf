"""Quick look at a footprint: pad rows, courtyard-ish extent and real 3D bounding box.

usage: python fpinfo.py part.kicad_mod [--pads]

The 3D box comes from dropping the footprint on an empty board and exporting an
STL with kicad-cli, so model offsets/rotations in the footprint are honoured.
Coordinates: x/y in footprint space, z above the board top (board 1.6 mm).
"""
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

from score import KICAD_CLI, stl_points
from sexpr import parse, find, first, value


BOARD = """(kicad_pcb (version 20260206) (generator "fpinfo") (generator_version "10.0")
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))
  (setup (pad_to_mask_clearance 0))
  (net 0 "")
  FOOTPRINT
)
"""


def bbox3d(mod_text, model_dir):
    with tempfile.TemporaryDirectory() as tmp:
        fp = mod_text.replace("${KIPRJMOD}", model_dir.replace("\\", "/"))

        def absolute(m):
            path = m.group(1)
            if not os.path.isabs(path) and not path.startswith("$"):
                path = os.path.join(model_dir, path).replace("\\", "/")
            return '(model "%s"' % path
        fp = re.sub(r'\(model "([^"]+)"', absolute, fp)
        fp = re.sub(r"^\(footprint \"([^\"]+)\"", r'(footprint "x:\1" (layer "F.Cu") (at 0 0)', fp.strip(), count=1)
        pcb = os.path.join(tmp, "t.kicad_pcb")
        open(pcb, "w", encoding="utf8").write(BOARD.replace("FOOTPRINT", fp))
        out = os.path.join(tmp, "t.stl")
        subprocess.run([KICAD_CLI, "pcb", "export", "stl", "-f", "--subst-models", "-o", out, pcb],
                       capture_output=True, text=True)
        if not os.path.exists(out):
            return None
        pts = stl_points(out)
        return pts.min(axis=0), pts.max(axis=0)


def pads(mod):
    rows = []
    for p in find(mod, "pad"):
        at = first(p, "at")
        size = first(p, "size")
        layers = first(p, "layers")
        rows.append((p[1], p[2], float(at[1]), float(at[2]), float(size[1]), float(size[2]),
                     " ".join(layers[1:]) if layers else ""))
    return rows


def main():
    path = sys.argv[1]
    text = open(path, encoding="utf8").read()
    mod = parse(text)
    rows = pads(mod)
    xs = [r[2] for r in rows]
    ys = [r[3] for r in rows]
    kinds = {}
    for r in rows:
        kinds[r[1]] = kinds.get(r[1], 0) + 1
    print(os.path.basename(path))
    print(f"  pads: {len(rows)} {kinds}  span x[{min(xs):.2f},{max(xs):.2f}] y[{min(ys):.2f},{max(ys):.2f}]")
    if "--pads" in sys.argv:
        for r in sorted(rows, key=lambda r: (r[3], r[2])):
            print(f"   {r[0]:>5} {r[1]:13s} ({r[2]:7.3f},{r[3]:7.3f}) {r[4]:.2f}x{r[5]:.2f} {r[6]}")
    box = bbox3d(text, os.path.dirname(os.path.dirname(os.path.abspath(path))))
    if box is not None:
        lo, hi = box
        print(f"  3D x[{lo[0]:.2f},{hi[0]:.2f}] y[{-hi[1]:.2f},{-lo[1]:.2f}] z[{lo[2]:.2f},{hi[2]:.2f}]"
              f"  -> {hi[0]-lo[0]:.2f} x {hi[1]-lo[1]:.2f}, height above board top {hi[2]:.2f}")


if __name__ == "__main__":
    main()
