"""Shrink the passives and drop the ones that don't do anything.

usage: python tools/shrink_passives.py <project dir> <current netlist>

Package choice is driven by the voltage on the part (from the netlist):
  * resistors 0402 -> 0201, except the 60R CAN terminations (~65 mW when the
    bus is dominant, too much for a 50 mW 0201)
  * caps up to 5 V -> 0201 (10 V parts); caps that see 12 V stay 0402 (25 V+)
  * 10 uF 0805 -> 0603 25 V on 12 V / 5 V, -> 0402 10 V on 3.3 V / VDDLDO
  * ferrite L3 0603 -> 0402

Removed / merged:
  * C6, C10: DNP feed-forward caps, never fitted
  * R38-R43: 0R links in the SD lines
  * R4/R5/R6 (3x 100k in parallel on the 3.3 V buck FB) -> R4 = 33k2
    (33.33k -> 33.2k shifts the output by 0.3 %)
  * R31/R32 and R44/R45 (2x 10k in parallel = USB-C Rd) -> R31, R44 = 5k1
"""
import os
import re
import sys

from sexpr import Q, parse, dumps, find, first, value
from netlist import load
from sch_edit import Sheet, pin_tip

HIGH_V = re.compile(r"^(\+12V|Net-\(U[12]-(BST|SW)\)|Net-\(J1-.*|Net-\(J[5-8]-VBUS.*|Net-\(D1.*|Net-\(Q1.*)$")

DROP = ["C6", "C10", "R5", "R6", "R32", "R45"]
SHORT = ["R38", "R39", "R40", "R41", "R42", "R43"]  # replace with a wire
VALUES = {"R4": "33k2", "R31": "5k1", "R44": "5k1"}
KEEP_0402 = {"R46", "R47", "R48", "R49"}

R0201 = "pcbgolf:R_0201_0603Metric"
C0201 = "pcbgolf:C_0201_0603Metric"
C0402 = "pcbgolf:0402-C"
C0603 = "pcbgolf:C_0603_1608Metric"
L0402 = "pcbgolf:L_0402_1005Metric"

CAP_MPN = {
    ("100nF", C0201): "GRM033R61A104KE15D",
    ("12pF", C0201): "GRM0335C1H120JA01D",
    ("220pF", C0201): "GRM0335C1H221JA01D",
    ("10u", C0603): "CL10A106KA8NRNC",
    ("10u", C0402): "GRM155R61A106ME11D",
}


def yageo_0201(val):
    v = val.upper().replace("R", "")
    if re.fullmatch(r"\d+", v) and int(v) < 1000:
        v = v + "R"
    return f"RC0201FR-07{v}L"


def plan(parts, nets_of):
    changes = {}
    for ref, p in parts.items():
        fp = p["footprint"].split(":")[-1]
        val = VALUES.get(ref, p["value"])
        hv = any(HIGH_V.match(n) for n in nets_of[ref])
        if ref in DROP or ref in SHORT:
            continue
        if ref.startswith("R") and fp == "0402-R" and ref not in KEEP_0402:
            changes[ref] = (R0201, val, yageo_0201(val))
        elif ref.startswith("C") and fp == "0402-C" and not ref.startswith("CH"):
            if hv or val.startswith("10u"):
                if val in ("10uF", "10u"):
                    changes[ref] = (C0603 if hv or "+5V" in nets_of[ref] else C0402, "10u", None)
                continue
            changes[ref] = (C0201, val, None)
        elif ref.startswith("C") and fp == "0805-C":
            fp_new = C0603 if (hv or "+5V" in nets_of[ref]) else C0402
            changes[ref] = (fp_new, "10u", None)
        elif ref == "L3":
            changes[ref] = (L0402, p["value"], "BLM15AG601SN1D")
    for ref, (fp, val, mpn) in list(changes.items()):
        if mpn is None:
            changes[ref] = (fp, val, CAP_MPN.get((val, fp)))
    return changes


def edit_sheet(path, changes):
    root = parse(open(path, encoding="utf8").read())
    sh = Sheet(root)
    touched = 0
    for sym in sh.symbols():
        ref = sh.ref(sym)
        if ref in DROP:
            sh.remove(sym)
            touched += 1
            continue
        if ref in SHORT:
            tips = pin_tip(sym, sh.libs[value(sym, "lib_id")])
            a, b = tips["1"][0], tips["2"][0]
            sh.remove(sym)
            sh.add_wire(a, b)
            touched += 1
            continue
        if ref not in changes:
            continue
        fp, val, mpn = changes[ref]
        for p in find(sym, "property"):
            if p[1] == "Footprint":
                p[2] = Q(fp)
            elif p[1] == "Value":
                p[2] = Q(val)
            elif p[1] == "MPN" and mpn:
                p[2] = Q(mpn)
        touched += 1
    if touched:
        sh.cleanup()
        libsec = first(root, "lib_symbols")
        used = {value(s, "lib_id") for s in sh.symbols()}
        for s in find(libsec, "symbol"):
            if s[1] not in used:
                libsec.remove(s)
        open(path, "w", encoding="utf8").write(dumps(root) + "\n")
    return touched


def main(proj, netfile):
    parts, nets, pins = load(netfile)
    nets_of = {r: set() for r in parts}
    for (r, _), n in pins.items():
        nets_of[r].add(n)
    changes = plan(parts, nets_of)
    total = 0
    for f in sorted(os.listdir(proj)):
        if f.endswith(".kicad_sch"):
            total += edit_sheet(os.path.join(proj, f), changes)
    print(f"{len(changes)} parts repackaged, {len(DROP) + len(SHORT)} removed, {total} symbols touched")
    for ref in sorted(changes, key=lambda r: (r[0], int(re.sub(r"\D", "", r)))):
        print(" ", ref, *changes[ref])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
