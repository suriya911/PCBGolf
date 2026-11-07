"""Footprint-only swaps: same pinout, smaller package.

usage: python tools/footprint_swaps.py <project dir>

D1  SMAJ16CA (SMB)          -> SMF16CA (SOD-123FL), same 16 V bidirectional TVS
                               family, 200 W instead of 400 W peak - it only has
                               to clamp hot-plug transients on the 12 V input
Y1  25 MHz 3225             -> 25 MHz 2016, same 1/3 crystal, 2/4 GND pinout
LED10-17 AM23ESGW (SOT-23)  -> Kingbright APTB1612 red/green 1.6x1.3, both cathodes -> C
Q2-Q9  QS5K2 (TSMT5)        -> DMG1026UV-7 (SOT-563), 60 V / 440 mA dual N; the 100R
                               relay pull-down from 12 V draws ~120 mA
SW1  EVQ-Q2 (3.1 mm tall)   -> EVQ-P7B01P side push, 1.35 mm tall, so it can sit on
                               a board edge inside the stack
"""
import os
import sys

from sexpr import Q, parse, dumps, find
from sch_edit import Sheet

SWAPS = {
    **{f"LED{n}": {"Footprint": "pcbgolf:LED_Bicolor_Kingbright_APTB1612", "MPN": "APTB1612SURKCGKC-F01"}
       for n in range(10, 18)},
    **{f"Q{n}": {"Footprint": "pcbgolf:SOT-563_DMG1026UV", "MPN": "DMG1026UV-7"} for n in range(2, 10)},
    "SW1": {"Footprint": "pcbgolf:SW_Panasonic_EVQ-P7B01P", "MPN": "EVQ-P7B01P"},
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
