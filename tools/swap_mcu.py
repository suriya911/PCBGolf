"""Replace the LQFP-144 STM32H725ZGT with the LQFP-100 STM32H725VGT on the MCU sheet.

usage: python tools/swap_mcu.py <project dir> <original netlist>

The old symbol is removed along with the wires that only existed to reach its
pins. The new symbol goes in the same spot and every pin gets a short stub with
a label (signals) or power symbol, using the remap in mcu_pinmap.py.
"""
import copy
import os
import re
import sys

from sexpr import Q, parse, dumps, find, first, value
from schgeom import lib_pins, pin_tip
from netlist import load
from sch_edit import Sheet, GRID, new_uuid, pin_outward, label_angle, move_group
from mcu_pinmap import REMAP, DROPPED

OLD_LIB = "pcbgolf:STM32H725ZGTx"
NEW_NAME = "STM32H725VGTx"
NEW_LIB = "pcbgolf:" + NEW_NAME
NEW_FP = "pcbgolf:LQFP-100_14x14mm_P0.5mm"
STOCK = os.path.expandvars(r"%LOCALAPPDATA%\Programs\KiCad\10.0\share\kicad\symbols\MCU_ST_STM32H7.kicad_sym")

POWER_SYMBOLS = {"GND": "pcbgolf:comma.ai_11112255_GND", "+3V3": "pcbgolf:+3V3"}
# rotation that makes each power symbol point away from the pin
GND_ROT = {(-1, 0): 270, (1, 0): 90, (0, 1): 0, (0, -1): 180}
VCC_ROT = {(-1, 0): 90, (1, 0): 270, (0, -1): 0, (0, 1): 180}


def base(name):
    return re.split(r"[(/]", name)[0]


def stock_symbol():
    root = parse(open(STOCK, encoding="utf8").read())
    sym = [s for s in find(root, "symbol") if s[1] == NEW_NAME][0]
    sym = copy.deepcopy(sym)
    sym[1] = Q(NEW_LIB)
    for p in find(sym, "property"):
        if p[1] == "Footprint":
            p[2] = Q(NEW_FP)
    return sym


def main(proj, netfile):
    path = os.path.join(proj, "pcbgolf_2.kicad_sch")
    root = parse(open(path, encoding="utf8").read())
    sh = Sheet(root)
    _, nets, _ = load(netfile)

    old = sh.by_ref("U3")
    old_lib = sh.libs[OLD_LIB]
    old_pins = {p["number"]: p for p in lib_pins(old_lib)}
    tips = pin_tip(old, old_lib)

    # signal name for every old pin name, straight from the original netlist
    net_of = {}
    for name, members in nets.items():
        for ref, pin, fn in members:
            if ref == "U3":
                net_of[base(old_pins[pin]["name"])] = name

    def readable(net):
        if not net.startswith("Net-("):
            return net
        m = re.match(r"Net-\(U3-(\w+)\)", net)
        pin = m.group(1)
        if pin in ("PH0", "PH1"):
            return {"PH0": "HSE_IN", "PH1": "HSE_OUT"}[pin]
        # SBU sense dividers: name after the SBU line on the far side of the resistor
        for ref, p, _ in nets[net]:
            if ref.startswith("R"):
                other = "2" if p == "1" else "1"
                for n2, mem in nets.items():
                    if (ref, other) in [(r, q) for r, q, _ in mem]:
                        return n2 + "_ADC"
        return "MCU_" + pin

    # 1. cut the wire stubs at the old pins; keep the far side alive with a label
    templates = {"global_label": find(root, "global_label")[0]}
    local_tmpl = copy.deepcopy(templates["global_label"])
    local_tmpl[0] = "label"
    local_tmpl[:] = [c for c in local_tmpl if not (isinstance(c, list) and c and c[0] in ("shape", "property", "fields_autoplaced"))]

    keep_labels = []
    for num, pts in tips.items():
        pname = base(old_pins[num]["name"])
        net = net_of.get(pname, "")
        for p in pts:
            for a, b, w in sh.wires():
                if p in (a, b):
                    far = b if p == a else a
                    sh.remove(w)
                    if net.startswith("Net-(") and pname not in DROPPED:
                        keep_labels.append((readable(net), far))
    for ref in DROPPED.values():
        sh.remove(sh.by_ref(ref))
    sh.remove(old)

    for text, far in keep_labels:
        sh.add_label(local_tmpl, text, far, 0)
    sh.cleanup()

    # 2. drop the old lib symbol, add the new one
    libsec = first(root, "lib_symbols")
    libsec.remove(old_lib)
    new_lib = stock_symbol()
    libsec.append(new_lib)
    sh.libs = {s[1]: s for s in find(libsec, "symbol")}

    # 3. new instance where the old one was
    inst = copy.deepcopy(old)
    first(inst, "lib_id")[1] = Q(NEW_LIB)
    first(inst, "uuid")[1] = new_uuid()
    for p in find(inst, "property"):
        if p[1] == "Value":
            p[2] = Q(NEW_NAME)
        elif p[1] == "Footprint":
            p[2] = Q(NEW_FP)
        elif p[1] in ("MPN", "Manufacturer Part Number"):
            p[2] = Q("STM32H725VGT6")
        elif p[1] == "Datasheet":
            p[2] = Q("https://www.st.com/resource/en/datasheet/stm32h725vg.pdf")
    inst[:] = [c for c in inst if not (isinstance(c, list) and c and c[0] == "pin")]
    new_pins = lib_pins(new_lib)
    for p in new_pins:
        inst.insert(len(inst) - 1, ["pin", Q(p["number"]), ["uuid", new_uuid()]])
    root.append(inst)

    inverse = {v: k for k, v in REMAP.items()}
    moved_away = set(REMAP)  # old names whose signal now lives elsewhere
    power_tmpl = {}
    for s in sh.symbols():
        lid = value(s, "lib_id")
        for net, lib in POWER_SYMBOLS.items():
            if lid == lib:
                power_tmpl[net] = s
    pwr_no = 900

    new_tips = pin_tip(inst, new_lib)
    done = set()
    for p in new_pins:
        # stacked power pins share one tip - one stub is enough
        if new_tips[p["number"]][0] in done:
            continue
        done.add(new_tips[p["number"]][0])
        name = base(p["name"])
        src = inverse.get(name)
        if src is None:
            src = None if name in moved_away else name
        net = net_of.get(src, "") if src else ""
        (tip,) = new_tips[p["number"]][:1]
        if not net or net.startswith("unconnected"):
            sh.add_no_connect(tip)
            continue
        out = pin_outward(p["rot"])
        end = (round(tip[0] + out[0] * GRID, 3), round(tip[1] + out[1] * GRID, 3))
        sh.add_wire(tip, end)
        if net in POWER_SYMBOLS:
            rot = (GND_ROT if net == "GND" else VCC_ROT)[out]
            pwr_no += 1
            sh.add_power(power_tmpl[net], end, rot, f"#PWR0{pwr_no}")
        elif net.startswith("Net-("):
            sh.add_label(local_tmpl, readable(net), end, label_angle(out))
        else:
            sh.add_label(templates["global_label"], net, end, label_angle(out))

    # the 100 pin symbol is narrower; pull the SBU sense dividers clear of its labels
    move_group(sh, ["R13", "R14", "R15", "R16"], -12.7, 0)
    move_group(sh, ["R17", "R18", "R19", "R20"], 17.78, 0)

    open(path, "w", encoding="utf8").write(dumps(root) + "\n")
    add_to_project_lib(os.path.join(proj, "pcbgolf.kicad_sym"))
    print("MCU swapped:", len(new_pins), "pins placed")


def add_to_project_lib(lib_path):
    """Keep the project symbol library in sync with the schematic's cached copy."""
    lib = parse(open(lib_path, encoding="utf8").read())
    lib[:] = [c for c in lib if not (isinstance(c, list) and c[:2] == ["symbol", NEW_NAME])]
    sym = stock_symbol()
    sym[1] = Q(NEW_NAME)
    lib.append(sym)
    open(lib_path, "w", encoding="utf8").write(dumps(lib) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
