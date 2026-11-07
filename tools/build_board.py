"""Generate one board of the stack from the schematic netlist.

Run with KiCad's bundled Python (needs pcbnew):
    "%LOCALAPPDATA%\\Programs\\KiCad\\10.0\\bin\\python.exe" tools/build_board.py \
        scratch/cur.net B0 placement/B0.json pcbgolf_B0.kicad_pcb

placement json: {"outline": [w, h], "parts": {"U3": [x, y, rot], ...}}
Parts of this board without a placement are dropped in a row below the
outline so nothing is silently lost. Only F.Cu carries copper; B.Cu exists
because KiCad needs two copper layers in the file but stays empty.
"""
import json
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
from netlist import load          # noqa: E402
from partition import board_of    # noqa: E402
import risers as riser_mod        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "pcbgolf.pretty")

TRACK = 0.127   # JLC 1-2 layer minimum is 5 mil
CLEARANCE = 0.127


POWER_PATTERNS = ["+12V", "+5V", "+3V3", "GND", "VBUS", "VDDLDO", "Net-(J*-VBUS*", "Net-(J1-PWR)"]


def write_project(out):
    """Board-local .kicad_pro: KiCad reads design rules and net classes from here."""
    proj = json.load(open(os.path.join(ROOT, "pcbgolf.kicad_pro")))
    rules = proj["board"]["design_settings"]["rules"]
    rules.update({
        "min_clearance": 0.1, "min_track_width": 0.1, "min_copper_edge_clearance": 0.2,
        "min_hole_clearance": 0.2, "min_hole_to_hole": 0.25, "min_through_hole_diameter": 0.5,
        "min_via_annular_width": 0.1, "min_text_height": 0.6, "min_text_thickness": 0.08,
    })
    classes = proj["net_settings"]["classes"]
    default = dict(classes[0])
    default.update({"name": "Default", "clearance": CLEARANCE, "track_width": TRACK})
    power = dict(default)
    power.update({"name": "Power", "track_width": 0.4, "priority": 0})
    proj["net_settings"]["classes"] = [default, power]
    proj["net_settings"]["netclass_patterns"] = [{"netclass": "Power", "pattern": p} for p in POWER_PATTERNS]
    proj["meta"]["filename"] = os.path.basename(out).replace(".kicad_pcb", ".kicad_pro")
    json.dump(proj, open(out.replace(".kicad_pcb", ".kicad_pro"), "w"), indent=2)


def mm(v):
    return pcbnew.FromMM(v)


def setup(board, thickness):
    board.SetCopperLayerCount(2)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(mm(thickness))
    ds.m_TrackMinWidth = mm(TRACK)
    ds.m_MinClearance = mm(CLEARANCE)
    ds.m_ViasMinSize = mm(0.45)
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetTrackWidth(mm(TRACK))
    nc.SetClearance(mm(CLEARANCE))


def outline(board, w, h):
    pts = [(0, 0), (w, 0), (w, h), (0, h)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(mm(x1), mm(y1)))
        seg.SetEnd(pcbnew.VECTOR2I(mm(x2), mm(y2)))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(mm(0.05))
        board.Add(seg)


def build(netfile, board_name, placement_file, out, thickness=0.6, risers_file=None):
    parts, nets, pins = load(netfile)
    place = json.load(open(placement_file)) if placement_file and os.path.exists(placement_file) else {}
    w, h = place.get("outline", [30, 30])
    where = place.get("parts", {})

    board = pcbnew.BOARD()
    setup(board, thickness)
    netinfo = {}
    for name in nets:
        if any(board_of(r) == board_name for r, _, _ in nets[name]):
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
            netinfo[name] = ni

    spare_x = 0.0
    for ref in sorted(parts):
        if board_of(ref) != board_name:
            continue
        lib_fp = parts[ref]["footprint"].split(":")[-1]
        fp = pcbnew.FootprintLoad(LIB, lib_fp)
        if fp is None:
            raise SystemExit(f"{ref}: footprint {lib_fp} not found")
        fp.SetReference(ref)
        fp.SetValue(parts[ref]["value"])
        if ref in where:
            x, y, rot = where[ref]
        else:
            x, y, rot = spare_x, h + 5, 0
            spare_x += 4
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            net = pins.get((ref, pad.GetNumber()))
            if net in netinfo:
                pad.SetNet(netinfo[net])
        board.Add(fp)

    if risers_file and os.path.exists(risers_file):
        boards = {}
        for name, members in nets.items():
            boards[name] = {board_of(r) for r, _, _ in members}
        riser_mod.add_to_board(board, riser_mod.load(risers_file), board_name,
                               lambda n: boards.get(n, set()), netinfo)

    outline(board, w, h)
    board.Save(out)
    write_project(out)
    print(f"{board_name}: {sum(1 for _ in board.GetFootprints())} footprints, {len(netinfo)} nets -> {out}")


if __name__ == "__main__":
    a = sys.argv[1:]
    build(a[0], a[1], a[2], a[3], float(a[4]) if len(a) > 4 else 0.6, a[5] if len(a) > 5 else None)
