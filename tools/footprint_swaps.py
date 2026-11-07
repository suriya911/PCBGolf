"""Footprint-only swaps: same pinout, smaller package.

usage: python tools/footprint_swaps.py <project dir>

D1  SMAJ16CA (SMB)          -> SMF16CA (SOD-123FL), same 16 V bidirectional TVS
                               family, 200 W instead of 400 W peak - it only has
                               to clamp hot-plug transients on the 12 V input
Y1  25 MHz 3225             -> 25 MHz 2016, same 1/3 crystal, 2/4 GND pinout
"""
import os
import sys

from sexpr import Q, parse, dumps, find
from sch_edit import Sheet

SWAPS = {
    "D1": {"Footprint": "pcbgolf:SOD-123F", "MPN": "SMF16CA"},
    "Y1": {"Footprint": "pcbgolf:Crystal_SMD_2016-4Pin_2.0x1.6mm", "MPN": "25MHz 2016-4P 12pF 20ppm"},
}


def main(proj):
    done = set()
    for f in sorted(os.listdir(proj)):
        if not f.endswith(".kicad_sch"):
            continue
        path = os.path.join(proj, f)
        root = parse(open(path, encoding="utf8").read())
        sh = Sheet(root)
        hit = False
        for s in sh.symbols():
            ref = sh.ref(s)
            if ref in SWAPS:
                for p in find(s, "property"):
                    if p[1] in SWAPS[ref]:
                        p[2] = Q(SWAPS[ref][p[1]])
                done.add(ref)
                hit = True
        if hit:
            open(path, "w", encoding="utf8").write(dumps(root) + "\n")
    print("repackaged:", sorted(done))


if __name__ == "__main__":
    main(sys.argv[1])
