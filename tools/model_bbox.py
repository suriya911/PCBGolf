"""Bounding boxes of STEP / VRML models, to line up vendor models with footprints."""
import re
import sys

import numpy as np

NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"


def step_bbox(path):
    t = open(path, errors="ignore").read()
    pts = re.findall(r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*(%s)\s*,\s*(%s)\s*,\s*(%s)\s*\)" % (NUM, NUM, NUM), t)
    a = np.array(pts, dtype=float)
    return a.min(0), a.max(0)


def wrl_bbox(path):
    t = open(path, errors="ignore").read()
    pts = []
    for blk in re.findall(r"point\s*\[(.*?)\]", t, re.S):
        n = list(map(float, re.findall(NUM, blk)))
        pts += [n[i:i + 3] for i in range(0, len(n) - 2, 3)]
    a = np.array(pts) * 2.54
    return a.min(0), a.max(0)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        lo, hi = (step_bbox if p.lower().endswith((".step", ".stp")) else wrl_bbox)(p)
        print(f"{p}\n   min {np.round(lo, 2)}  max {np.round(hi, 2)}  size {np.round(hi - lo, 2)}")
