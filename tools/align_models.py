"""Line up EasyEDA STEP models with their footprints.

EasyEDA ships a VRML model that sits correctly on the footprint and a vendor
STEP that often doesn't (different origin). KiCad's STEP/STL export uses the
STEP, so a bad origin silently breaks the 3D assembly and the volume score.

For each footprint: place it alone on a test board, export an STL, measure the
STEP model's box in footprint coordinates, compare with the VRML box and write
the difference into the footprint's (model (offset ...)).

usage (KiCad python):  python tools/align_models.py <footprint name> <vrml file> [...pairs]
"""
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
from model_bbox import wrl_bbox   # noqa: E402
from score import stl_points      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "pcbgolf.pretty")
CLI = os.path.join(os.path.dirname(sys.executable), "kicad-cli.exe")
THICK = 1.6


def step_box(fp_name):
    board = pcbnew.BOARD()
    board.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(THICK))
    fp = pcbnew.FootprintLoad(LIB, fp_name)
    fp.SetPosition(pcbnew.VECTOR2I(0, 0))
    for m in fp.Models():
        m.m_Offset = pcbnew.VECTOR3D(0, 0, 0)
    board.Add(fp)
    tmp = tempfile.mkdtemp(dir=ROOT)
    pcb = os.path.join(tmp, "t.kicad_pcb")
    board.Save(pcb)
    stl = os.path.join(tmp, "t.stl")
    subprocess.run([CLI, "pcb", "export", "stl", "-f", "--subst-models", "--no-board-body",
                    "-D", f"KIPRJMOD={ROOT}", "-o", stl, pcb], capture_output=True)
    pts = stl_points(stl)
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)
    # STL: y is up (= -KiCad y), z = 0 at the bottom of the board
    lo, hi = pts.min(0), pts.max(0)
    model_lo = np.array([lo[0], lo[1], lo[2] - THICK])   # model coords: y up, z from board top
    model_hi = np.array([hi[0], hi[1], hi[2] - THICK])
    return model_lo, model_hi


def align(fp_name, wrl):
    s_lo, s_hi = step_box(fp_name)
    w_lo, w_hi = wrl_bbox(wrl)
    size_s, size_w = s_hi - s_lo, w_hi - w_lo
    if np.any(np.abs(size_s - size_w) > 0.3):
        print(f"{fp_name}: STEP {np.round(size_s, 2)} vs VRML {np.round(size_w, 2)} - shapes differ, not touching it")
        return
    off = (w_lo + w_hi) / 2 - (s_lo + s_hi) / 2
    path = os.path.join(LIB, fp_name + ".kicad_mod")
    text = open(path, encoding="utf8").read()
    text = re.sub(r"\(offset\s*\(xyz [^)]*\)\)", "(offset (xyz %.3f %.3f %.3f))" % tuple(off), text, count=1)
    open(path, "w", encoding="utf8").write(text)
    print(f"{fp_name}: offset {np.round(off, 3)}")


if __name__ == "__main__":
    args = sys.argv[1:]
    for name, wrl in zip(args[::2], args[1::2]):
        align(name, wrl)
