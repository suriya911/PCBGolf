"""OPA197 SOIC-8 -> OPA197 SOT-23-5 (DBV) for the four CAN activity comparators.

usage: python tools/swap_opamp.py <project dir> <current netlist>

Same die, same supply (12 V) - only the package changes. SOIC-8 pins
2(-) 3(+) 4(V-) 6(OUT) 7(V+) map onto DBV 4 3 2 1 5; NC pins 1/5/8 go away.
"""
import os
import sys

from sexpr import parse, dumps, find, first, value
from netlist import load
from sch_edit import Sheet, PartAdder, add_lib_symbol, flatten_symbol, replace_part

KICAD_SYM = os.path.expandvars(r"%LOCALAPPDATA%\Programs\KiCad\10.0\share\kicad\symbols")
PIN_MAP = {"6": "1", "4": "2", "3": "3", "2": "4", "7": "5"}
TAGS = {"2": "INN", "3": "INP", "6": "OUT"}
LIB_ID = "pcbgolf:OPA197xDBV"
FOOTPRINT = "pcbgolf:SOT23-5"
REFS = ["U9", "U10", "U11", "U12"]


def main(proj, netfile):
    _, nets, _ = load(netfile)
    path = os.path.join(proj, "pcbgolf_4.kicad_sch")
    root = parse(open(path, encoding="utf8").read())
    sh = Sheet(root)
    lib_root = parse(open(os.path.join(KICAD_SYM, "Amplifier_Operational.kicad_sym"), encoding="utf8").read())
    sym = flatten_symbol(lib_root, "OPA196xDBV", LIB_ID)
    for p in find(sym, "property"):
        if p[1] == "Footprint":
            p[2] = type(p[2])(FOOTPRINT)
        elif p[1] == "Value":
            p[2] = type(p[2])("OPA197xDBV")
    add_lib_symbol(sh, sym, LIB_ID)

    global_nets = set()
    for f in os.listdir(proj):
        if f.endswith(".kicad_sch"):
            src = root if f == "pcbgolf_4.kicad_sch" else parse(open(os.path.join(proj, f), encoding="utf8").read())
            global_nets |= {lab[1] for lab in find(src, "global_label")}
    template = sh.by_ref(REFS[0])
    import copy
    adder = PartAdder(sh, copy.deepcopy(template), global_nets)

    for ref in REFS:
        old_nets = {p: n for n, m in nets.items() for r, p, _ in m if r == ref}
        replace_part(sh, adder, ref, LIB_ID, PIN_MAP, old_nets, FOOTPRINT, "OPA197IDBVR",
                     props={"MPN": "OPA197IDBVR"}, label_for=lambda pin, ref=ref: f"{ref}_{TAGS[pin]}")

    libsec = first(root, "lib_symbols")
    used = {value(s, "lib_id") for s in sh.symbols()}
    for s in find(libsec, "symbol"):
        if s[1] not in used:
            libsec.remove(s)
    open(path, "w", encoding="utf8").write(dumps(root) + "\n")

    lib_path = os.path.join(proj, "pcbgolf.kicad_sym")
    lib = parse(open(lib_path, encoding="utf8").read())
    lib[:] = [c for c in lib if not (isinstance(c, list) and c[:1] == ["symbol"] and c[1] == "OPA197xDBV")]
    s = copy.deepcopy(sym)
    s[1] = type(s[1])("OPA197xDBV")
    lib.append(s)
    open(lib_path, "w", encoding="utf8").write(dumps(lib) + "\n")
    print("op-amps swapped:", ", ".join(REFS))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
