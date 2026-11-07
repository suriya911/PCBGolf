"""Replace the USB2517 (QFN-64, 9x9) hub with two cascaded CH334R (QSOP-16).

usage: python tools/swap_hub.py <project dir>

Topology after the swap:
    J3 (host) -> U4 CH334R  port1 -> CH1, port2 -> CH2, port3 -> CH3, port4 -> U17
                 U17 CH334R port1 -> CH4, port2 -> MCU, ports 3/4 unused

Why: the USB2517 only has ground on its exposed pad and needs a 24 MHz crystal,
two 1.8 V rails with four caps, a bias resistor and SMBus pull-ups. The CH334R
is a leaded part with a real GND pin (routable on one copper layer), runs
straight off 3.3 V, has its crystal load caps built in and needs no config bus.
The MCU's HUB_SCL/HUB_SDA pins are left unconnected.
"""
import copy
import os
import sys

from sexpr import Q, parse, dumps, find, first, value
from sch_edit import Sheet, PartAdder, add_lib_symbol

KICAD_SYM = os.path.expandvars(r"%LOCALAPPDATA%\Programs\KiCad\10.0\share\kicad\symbols")

REMOVE = ["U4", "Y2", "C28", "C32", "C33", "C34", "C35", "C36",
          "R24", "R25", "R26", "R27", "R28", "R29", "R30"]

HUB_FP = "pcbgolf:QSOP-16_3.9x4.9mm_P0.635mm"
XTAL_FP = "pcbgolf:Crystal_SMD_2016-4Pin_2.0x1.6mm"


def hub_nets(up_n, up_p, ports, xtal):
    """CH334R pin numbers -> nets. ports is a list of 4 (dm, dp) tuples or None."""
    nets = {"10": up_n, "11": up_p, "12": "+3V3", "13": "+3V3", "14": "GND",
            "16": xtal + "_XI", "15": xtal + "_XO", "9": None}
    pinmap = [("7", "8"), ("5", "6"), ("3", "4"), ("1", "2")]  # DM1/DP1 .. DM4/DP4
    for (dm, dp), port in zip(pinmap, ports):
        nets[dm] = port[0] if port else None
        nets[dp] = port[1] if port else None
    return nets


def stock(lib, name):
    root = parse(open(os.path.join(KICAD_SYM, lib + ".kicad_sym"), encoding="utf8").read())
    return [s for s in find(root, "symbol") if s[1] == name][0]


def hub_symbol():
    """Stock CH334R, with VDD33 typed as a supply input: we feed it 3.3 V (V5 tied to VDD33)."""
    sym = copy.deepcopy(stock("Interface_USB", "CH334R"))
    for p in find(sym, "property"):
        if p[1] == "Footprint":
            p[2] = Q(HUB_FP)

    def walk(node):
        for c in node[1:]:
            if isinstance(c, list) and c:
                if c[0] == "pin" and value(c, "number") == "13":
                    c[1] = "power_in"
                else:
                    walk(c)
    walk(sym)
    return sym


def add_to_project_lib(lib_path, symbols):
    lib = parse(open(lib_path, encoding="utf8").read())
    lib[:] = [c for c in lib if not (isinstance(c, list) and c[:1] == ["symbol"] and c[1] in symbols)]
    for name, sym in symbols.items():
        s = copy.deepcopy(sym)
        s[1] = Q(name)
        lib.append(s)
    open(lib_path, "w", encoding="utf8").write(dumps(lib) + "\n")


def main(proj):
    path = os.path.join(proj, "pcbgolf_3.kicad_sch")
    root = parse(open(path, encoding="utf8").read())
    sh = Sheet(root)

    template = copy.deepcopy(sh.by_ref("U4"))
    for ref in REMOVE:
        sh.remove(sh.by_ref(ref))
    # the SMBus config lines go away with the USB2517
    for _, lab in sh.label_nodes():
        if lab[1] in ("HUB_SCL", "HUB_SDA"):
            sh.remove(lab)
    sh.cleanup()
    libsec = first(root, "lib_symbols")
    used = {value(s, "lib_id") for s in sh.symbols()}
    for s in find(libsec, "symbol"):
        if s[1] not in used:
            libsec.remove(s)

    hub_sym = hub_symbol()
    add_lib_symbol(sh, hub_sym, "pcbgolf:CH334R")
    xtal_sym = stock("Device", "Crystal_GND24")
    add_lib_symbol(sh, xtal_sym, "pcbgolf:Crystal_GND24")
    add_to_project_lib(os.path.join(proj, "pcbgolf.kicad_sym"), {"CH334R": hub_sym, "Crystal_GND24": xtal_sym})

    # global labels can live on any sheet of the project
    global_nets = set()
    for f in os.listdir(proj):
        if f.endswith(".kicad_sch"):
            other = path if f == "pcbgolf_3.kicad_sch" else os.path.join(proj, f)
            src = root if other == path else parse(open(other, encoding="utf8").read())
            global_nets |= {lab[1] for lab in find(src, "global_label")}
    add = PartAdder(sh, template, global_nets)

    ports_a = [("CH1_D_N", "CH1_D_P"), ("CH2_D_N", "CH2_D_P"), ("CH3_D_N", "CH3_D_P"),
               ("HUB2_D_N", "HUB2_D_P")]
    ports_b = [("CH4_D_N", "CH4_D_P"), ("STM_D_N", "STM_D_P"), None, None]
    hub_props = {"MPN": "CH334R", "LCSC": "C4154405", "Manufacturer": "WCH"}
    add.add("pcbgolf:CH334R", "U4", "CH334R", HUB_FP, (101.6, 152.4),
            hub_nets("USB_D_N", "USB_D_P", ports_a, "HUB1"), props=hub_props)
    add.add("pcbgolf:CH334R", "U17", "CH334R", HUB_FP, (149.86, 152.4),
            hub_nets("HUB2_D_N", "HUB2_D_P", ports_b, "HUB2"), props=hub_props)

    # any 12 MHz 2016 crystal, 12-20 pF load, <=20 ppm (CH334 datasheet); pick from JLC stock at order time
    xtal_props = {"MPN": "12MHz 2016-4P 12-20pF 20ppm"}
    add.add("pcbgolf:Crystal_GND24", "Y2", "12MHz", XTAL_FP, (101.6, 111.76),
            {"1": "HUB1_XI", "3": "HUB1_XO", "2": "GND", "4": "GND"}, props=xtal_props)
    add.add("pcbgolf:Crystal_GND24", "Y3", "12MHz", XTAL_FP, (149.86, 111.76),
            {"1": "HUB2_XI", "3": "HUB2_XO", "2": "GND", "4": "GND"}, props=xtal_props)

    # one 10u bulk cap per hub, next to the 100n ones (C30/C31) that already sit on +3V3
    cap = sh.by_ref("C29")
    cap_lib = value(cap, "lib_id")
    cap_props = {p[1]: p[2] for p in find(cap, "property") if p[1] not in ("Reference", "Value", "Footprint")}
    cap_fp = [p[2] for p in find(cap, "property") if p[1] == "Footprint"][0]
    add.add(cap_lib, "C33", "10u", cap_fp, (170.18, 111.76), {"1": "+3V3", "2": "GND"}, props=cap_props)
    add.add(cap_lib, "C34", "10u", cap_fp, (180.34, 111.76), {"1": "+3V3", "2": "GND"}, props=cap_props)

    open(path, "w", encoding="utf8").write(dumps(root) + "\n")
    free_mcu_i2c(os.path.join(proj, "pcbgolf_2.kicad_sch"))
    print("hub swapped")


def free_mcu_i2c(path):
    """PB10/PB11 only talked SMBus to the USB2517 - mark them not connected."""
    from schgeom import pin_tip
    root = parse(open(path, encoding="utf8").read())
    sh = Sheet(root)
    for _, lab in sh.label_nodes():
        if lab[1] in ("HUB_SCL", "HUB_SDA"):
            sh.remove(lab)
    sh.cleanup()
    mcu = sh.by_ref("U3")
    names = {}
    from schgeom import lib_pins
    lib = sh.libs[value(mcu, "lib_id")]
    for p in lib_pins(lib):
        names[p["number"]] = p["name"]
    tips = pin_tip(mcu, lib)
    for num, name in names.items():
        if name in ("PB10", "PB11"):
            sh.add_no_connect(tips[num][0])
    open(path, "w", encoding="utf8").write(dumps(root) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
