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
    import_easyeda(src, "C719027", "microSD_Hirose_DM3D-SF", "Connector_Card.3dshapes",
                   {"9": "", "10": "", "11": "G1", "12": "G2", "13": "G3", "14": "G4"})
    pj083ah()


if __name__ == "__main__":
    main(sys.argv[1])
