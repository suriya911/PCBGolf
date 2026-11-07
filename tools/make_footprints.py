"""Build the project footprints for the new connectors.

usage: python tools/make_footprints.py <easyeda download dir>

* USB-C 24P QT (SHOU HAN, LCSC C2681555) - EasyEDA footprint, shell pads renamed
  to SH so they line up with the stock USB_C_Receptacle symbol.
* microSD DM3D-SF (Hirose, LCSC C719027) - EasyEDA footprint, shell tabs 11-14
  renamed G1-G4 to match the existing J2 symbol; 9/10 are the card-detect
  switch, which the original design never used, so they stay as plain
  mechanical pads with no net.
* DC jack PJ-083AH (Same Sky) - drawn from the recommended PCB layout in the
  datasheet (rev 09/19/2024). Pad names follow the existing J1 symbol:
  terminal 1 (centre pin) = PWR1, terminal 3 (sleeve) = GND,
  terminal 2 (switch) = GNDBREAK. Origin = jack centre-line at the front face.
"""
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRETTY = os.path.join(ROOT, "pcbgolf.pretty")
SHAPES = os.path.join(ROOT, "pcbgolf.3dshapes")


def drop_pads(path, at_list):
    """Remove pads at the given (x, y) positions (duplicate vendor pads)."""
    sys.path.insert(0, os.path.dirname(__file__))
    from sexpr import parse, dumps, find, first
    mod = parse(open(path, encoding="utf8").read())
    keep = []
    for c in mod:
        if isinstance(c, list) and c and c[0] == "pad":
            at = first(c, "at")
            if any(abs(float(at[1]) - x) < 0.01 and abs(float(at[2]) - y) < 0.01 for x, y in at_list):
                continue
        keep.append(c)
    mod[:] = keep
    open(path, "w", encoding="utf8").write(dumps(mod) + "\n")


def nudge_pads(path, moves):
    """Move pads: {(x, y): (new_x, new_y)}."""
    sys.path.insert(0, os.path.dirname(__file__))
    from sexpr import parse, dumps, find, first
    mod = parse(open(path, encoding="utf8").read())
    for pad in find(mod, "pad"):
        at = first(pad, "at")
        for (x, y), (nx, ny) in moves.items():
            if abs(float(at[1]) - x) < 0.01 and abs(float(at[2]) - y) < 0.01:
                at[1], at[2] = f"{nx:g}", f"{ny:g}"
    open(path, "w", encoding="utf8").write(dumps(mod) + "\n")


def single_layer(path, ring, min_round=0.5, min_slot=1.0, keep_ring=None):
    """JLC single-sided boards have no plated holes, so every through-hole pad becomes
    an NPTH with a copper ring on F.Cu only. Holes grow to the fab minimums (0.5 mm
    round, 1.0 mm slot width), the copper ring is `ring` all round. Holes without
    copper (locating pegs) become plain NPTH. keep_ring: {pad name: ring} overrides.
    """
    sys.path.insert(0, os.path.dirname(__file__))
    from sexpr import Q, parse, dumps, find, first
    mod = parse(open(path, encoding="utf8").read())
    for pad in find(mod, "pad"):
        if pad[2] != "thru_hole":
            continue
        size = first(pad, "size")
        drill = first(pad, "drill")
        oval = drill[1] == "oval"
        dx = float(drill[2] if oval else drill[1])
        dy = float(drill[3]) if oval else dx
        sx, sy = float(size[1]), float(size[2])
        pad[2] = "np_thru_hole"
        layers = first(pad, "layers")
        if sx <= dx + 1e-3 and sy <= dy + 1e-3:          # bare locating hole
            d = max(dx, min_round)
            pad[1] = Q("")
            pad[3] = "circle"
            size[1:] = [f"{d:g}", f"{d:g}"]
            drill[1:] = [f"{d:g}"]
            layers[1:] = [Q("*.Cu"), Q("*.Mask")]
            continue
        if oval:
            if dx <= dy:
                dx = max(dx, min_slot); dy = max(dy, dx + 0.01)
            else:
                dy = max(dy, min_slot); dx = max(dx, dy + 0.01)
            drill[1:] = ["oval", f"{dx:.3f}", f"{dy:.3f}"]
        else:
            dx = dy = max(dx, min_round)
            drill[1:] = [f"{dx:.3f}"]
        r = (keep_ring or {}).get(pad[1], ring)
        size[1:] = [f"{dx + 2 * r:.3f}", f"{dy + 2 * r:.3f}"]
        layers[1:] = [Q("F.Cu"), Q("F.Mask")]
    open(path, "w", encoding="utf8").write(dumps(mod) + "\n")


def model_line(sub, name):
    return f'(model "${{KIPRJMOD}}/pcbgolf.3dshapes/{sub}/{name}"'


def import_easyeda(src_dir, lcsc, new_name, sub3d, rename):
    pretty = os.path.join(src_dir, f"lib_{lcsc}.pretty")
    mod = [f for f in os.listdir(pretty) if f.endswith(".kicad_mod")][0]
    text = open(os.path.join(pretty, mod), encoding="utf8").read()
    shapes = os.path.join(src_dir, f"lib_{lcsc}.3dshapes")
    step = [f for f in os.listdir(shapes) if f.lower().endswith(".step")][0]
    os.makedirs(os.path.join(SHAPES, sub3d), exist_ok=True)
    shutil.copy(os.path.join(shapes, step), os.path.join(SHAPES, sub3d, new_name + ".step"))
    text = re.sub(r'\(model "[^"]*"', model_line(sub3d, new_name + ".step"), text)
    text = re.sub(r'^\(footprint "[^"]*"', f'(footprint "{new_name}"', text, count=1)
    def pad_name(m):
        name = m.group(1).strip('"')
        return f'(pad "{rename.get(name, name)}" '
    text = re.sub(r'\(pad ("[^"]*"|\S+) ', pad_name, text)
    open(os.path.join(PRETTY, new_name + ".kicad_mod"), "w", encoding="utf8").write(text)
    print("wrote", new_name)


def slot(name, x, y, hole_w, hole_h, pad_w, pad_h):
    return (f'\t(pad "{name}" thru_hole oval (at {x:g} {y:g}) (size {pad_w:g} {pad_h:g}) '
            f'(drill oval {hole_w:g} {hole_h:g}) (layers "*.Cu" "*.Mask"))\n')


def pj083ah():
    # datasheet frame: x from the front face (plug side) backwards, y up, origin on the axis
    # we flip y for KiCad (y down)
    pads = [
        slot("PWR1", 11.25, 0.0, 0.8, 2.0, 1.3, 2.5),       # terminal 1, vertical slot
        slot("GNDBREAK", 10.30, -5.20, 2.0, 0.8, 2.5, 1.3),  # terminal 2
        slot("GND", 10.30, -3.10, 2.0, 0.8, 2.5, 1.3),       # terminal 3
        slot("", 3.00, -6.10, 2.3, 0.8, 2.8, 1.3),           # shield tabs, mechanical
        slot("", 3.00, 3.70, 2.3, 0.8, 2.8, 1.3),
        '\t(pad "" np_thru_hole circle (at 4 0) (size 2.5 2.5) (drill 2.5) (layers "*.Cu" "*.Mask"))\n',
    ]
    body = [(0, -6.2), (11.5, -6.2), (11.5, 3.8), (0, 3.8)]

    def poly(layer, pts, width):
        lines = ""
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            lines += (f'\t(fp_line (start {x1:g} {y1:g}) (end {x2:g} {y2:g}) '
                      f'(stroke (width {width:g}) (type solid)) (layer "{layer}"))\n')
        return lines

    crt = [(-0.25, -6.45), (12.15, -6.45), (12.15, 4.05), (-0.25, 4.05)]
    text = (
        '(footprint "DC_Jack_SameSky_PJ-083AH"\n'
        '\t(version 20260206)\n\t(generator "make_footprints.py")\n\t(layer "F.Cu")\n'
        '\t(descr "DC power jack 5.5/2.0 mm, 5 A, through hole, 7.2 mm tall. '
        'https://www.sameskydevices.com/product/resource/pj-083ah.pdf")\n'
        '\t(tags "barrel jack dc power")\n'
        '\t(property "Reference" "REF**" (at 5.75 -7.2 0) (layer "F.SilkS") '
        '(effects (font (size 0.8 0.8) (thickness 0.12))))\n'
        '\t(property "Value" "PJ-083AH" (at 5.75 5 0) (layer "F.Fab") '
        '(effects (font (size 0.8 0.8) (thickness 0.12))))\n'
        '\t(attr through_hole)\n'
        + poly("F.Fab", body, 0.1) + poly("F.CrtYd", crt, 0.05)
        + "".join(pads)
        + '\t' + model_line("Connector_BarrelJack.3dshapes", "PJ-083AH_clipped.step")
        + '\n\t\t(offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))\n'
        ')\n'
    )
    open(os.path.join(PRETTY, "DC_Jack_SameSky_PJ-083AH.kicad_mod"), "w", encoding="utf8").write(text)
    print("wrote DC_Jack_SameSky_PJ-083AH")


def main(src):
    import_easyeda(src, "C2681555", "USB_C_Receptacle_ShouHan_TYPE-C-24P-QT", "Connector_USB.3dshapes",
                   {"25": "SH", "3": "SH", "4": "SH"})
    # EasyEDA draws each rear shell leg as two overlapping slots; one hole per leg is enough
    drop_pads(os.path.join(PRETTY, "USB_C_Receptacle_ShouHan_TYPE-C-24P-QT.kicad_mod"),
              [(4.05, -1.47), (-4.08, -1.47)])
    # the 1.0 mm slot is twice the tab thickness; move the rear slots 0.1 mm outward so the
    # hole stays 0.2 mm from the B1/B12 pads (the tab still sits fully inside the slot)
    nudge_pads(os.path.join(PRETTY, "USB_C_Receptacle_ShouHan_TYPE-C-24P-QT.kicad_mod"),
               {(4.32, -2.03): (4.42, -2.03), (-4.32, -2.03): (-4.42, -2.03)})
    # shell tabs sit 0.15 mm from the outer signal pads: only a 0.25 mm ring fits
    single_layer(os.path.join(PRETTY, "USB_C_Receptacle_ShouHan_TYPE-C-24P-QT.kicad_mod"), ring=0.25)
    import_easyeda(src, "C719027", "microSD_Hirose_DM3D-SF", "Connector_Card.3dshapes",
                   {"9": "", "10": "", "11": "G1", "12": "G2", "13": "G3", "14": "G4"})
    # SBU indicator: Kingbright bicolor 1.6x1.3 (pins 1/3 anodes, 2/4 cathodes) for the SOT-23 AM23ESGW
    import_easyeda(src, "C6506889", "LED_Bicolor_Kingbright_APTB1612", "LED_SMD.3dshapes",
                   {"1": "AR", "3": "AG", "2": "C", "4": "C"})
    # SBU switches: DMG1026UV dual N 60 V SOT-563 for the TSMT5 QS5K2; both sources -> pin 2 (S)
    import_easyeda(src, "C508194", "SOT-563_DMG1026UV", "Package_TO_SOT_SMD.3dshapes",
                   {"1": "2", "2": "1", "3": "4", "4": "2", "5": "3", "6": "5"})
    # boot/user button: Panasonic EVQ-P7 side push, 1.35 mm tall, for the 3.1 mm EVQ-Q2
    import_easyeda(src, "C485515", "SW_Panasonic_EVQ-P7B01P", "Button_Switch_SMD.3dshapes",
                   {"1": "A", "1'": "A'", "2": "B", "2'": "B'"})
    pj083ah()
    single_layer(os.path.join(PRETTY, "DC_Jack_SameSky_PJ-083AH.kicad_mod"), ring=0.45)


if __name__ == "__main__":
    main(sys.argv[1])
