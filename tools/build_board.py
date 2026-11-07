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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "pcbgolf.pretty")

TRACK = 0.127   # JLC 1-2 layer minimum is 5 mil
CLEARANCE = 0.127


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


def build(netfile, board_name, placement_file, out, thickness=0.6):
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

    outline(board, w, h)
    board.Save(out)
    print(f"{board_name}: {sum(1 for _ in board.GetFootprints())} footprints, {len(netinfo)} nets -> {out}")


if __name__ == "__main__":
    build(*sys.argv[1:5])
