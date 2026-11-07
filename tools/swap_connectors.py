"""Connector changes.

usage: python tools/swap_connectors.py <project dir> <current netlist>

* J5-J8 (OBD-C ports) and J3 (host): vertical GCT 10132328 / JAE DX07 ->
  SHOU HAN TYPE-C 24P QT, a full 24-contact right-angle SMT receptacle
  (3.2 mm tall instead of ~9 mm). Both pad rows sit behind the shell legs, the
  rear row escapes backwards and the front row forwards under the shell, so the
  connector can be fanned out on a single copper layer. comma's symbols are
  kept; their shell pins collapse into one SH pin (the QT shell has 6 tabs).
* J2 microSD: Molex 47219 (14.6x15.2) -> Hirose DM3D-SF (12.0x11.5x1.6),
  footprint-only change.
* J1 DC jack: CUI PJ-002AH-SMT (11 mm tall) -> Same Sky PJ-083AH, same
  5.5/2.0 mm plug, 5 A, 7.2 mm tall, footprint-only change.
"""
import copy
import os
import re
import sys

from sexpr import Q, parse, dumps, find, first, value
from netlist import load
from sch_edit import Sheet, new_uuid

KICAD_SYM = os.path.expandvars(r"%LOCALAPPDATA%\Programs\KiCad\10.0\share\kicad\symbols")
USB_LIB = "pcbgolf:USB_C_Receptacle"
USB_FP = "pcbgolf:USB_C_Receptacle_ShouHan_TYPE-C-24P-QT"
USB_PROPS = {"MPN": "TYPE-C 24P QT", "LCSC": "C2681555", "Manufacturer": "SHOU HAN"}
PORT_NAME = {"J5": "CH1", "J6": "CH2", "J7": "CH3", "J8": "CH4", "J3": "USB"}

FOOTPRINT_ONLY = {
    "J2": {"Footprint": "pcbgolf:microSD_Hirose_DM3D-SF", "MPN": "DM3D-SF", "LCSC": "C719027"},
    "J1": {"Footprint": "pcbgolf:DC_Jack_SameSky_PJ-083AH", "MPN": "PJ-083AH"},
}


def trim_usb_symbol(lib_sym):
    """Keep comma's compact receptacle symbol: drop the duplicate contacts.

    All shell pins (S1..S14, S1B, S1T...) collapse into one pin "SH" and the
    DX07's top-side copies of the B row (B1T...) go away - they were the same
    contacts on the old part. Returns the set of removed pin numbers.
    """
    removed = set()
    kept_shell = False

    def walk(node):
        nonlocal kept_shell
        keep = []
        for c in node:
            if isinstance(c, list) and c and c[0] == "pin":
                num = value(c, "number")
                if num.startswith("S"):
                    if kept_shell:
                        removed.add(num)
                        continue
                    kept_shell = True
                    first(c, "number")[1] = Q("SH")
                    first(c, "name")[1] = Q("SHIELD")
                    removed.add(num)
                elif re.fullmatch(r"B\d+T", num):
                    removed.add(num)
                    continue
            elif isinstance(c, list) and c and c[0] == "symbol":
                walk(c)
            keep.append(c)
        node[:] = keep
    walk(lib_sym)
    return removed


def global_labels(proj, skip, skip_root):
    out = set()
    for f in os.listdir(proj):
        if f.endswith(".kicad_sch"):
            src = skip_root if f == skip else parse(open(os.path.join(proj, f), encoding="utf8").read())
            out |= {lab[1] for lab in find(src, "global_label")}
    return out


def main(proj, netfile):

    for f in sorted(os.listdir(proj)):
        if not f.endswith(".kicad_sch"):
            continue
        path = os.path.join(proj, f)
        root = parse(open(path, encoding="utf8").read())
        sh = Sheet(root)
        refs = {sh.ref(s) for s in sh.symbols()}
        touched = False

        for ref, props in FOOTPRINT_ONLY.items():
            if ref in refs:
                for p in find(sh.by_ref(ref), "property"):
                    if p[1] in props:
                        p[2] = Q(props[p[1]])
                touched = True

        usb_libs = {value(sh.by_ref(r), "lib_id") for r in refs if r in PORT_NAME}
        for lib_id in usb_libs:
            # trim the shared lib symbol, drop the instance pin entries, then tidy dangling wires
            insts = [s for s in sh.symbols() if value(s, "lib_id") == lib_id]
            removed = trim_usb_symbol(sh.libs[lib_id])
            for s in insts:
                s[:] = [c for c in s if not (isinstance(c, list) and c and c[0] == "pin" and c[1] in removed)]
                s.insert(len(s) - 1, ["pin", Q("SH"), ["uuid", new_uuid()]])
                for p in find(s, "property"):
                    if p[1] == "Footprint":
                        p[2] = Q(USB_FP)
                    elif p[1] in USB_PROPS:
                        p[2] = Q(USB_PROPS[p[1]])
                for k, v in USB_PROPS.items():
                    if k not in [p[1] for p in find(s, "property")]:
                        s.insert(len(s) - 1, ["property", Q(k), Q(v), ["at", "0", "0", "0"],
                                              ["effects", ["font", ["size", "1.27", "1.27"]], ["hide", "yes"]]])
            sh.cleanup()
            touched = True

        if touched:
            libsec = first(root, "lib_symbols")
            used = {value(s, "lib_id") for s in sh.symbols()}
            for s in find(libsec, "symbol"):
                if s[1] not in used:
                    libsec.remove(s)
            open(path, "w", encoding="utf8").write(dumps(root) + "\n")
            print("updated", f)

    sync_project_lib(proj)


def sync_project_lib(proj):
    """Trim the same symbols in the project library so it matches the sheets."""
    lib_path = os.path.join(proj, "pcbgolf.kicad_sym")
    lib = parse(open(lib_path, encoding="utf8").read())
    for s in find(lib, "symbol"):
        if s[1] in ("comma.ai_11112255_USB-C-FEMALEGCT", "comma.ai_11112255_USB-C-FEMALE"):
            trim_usb_symbol(s)
    open(lib_path, "w", encoding="utf8").write(dumps(lib) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
