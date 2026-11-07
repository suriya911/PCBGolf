"""PCBGolf score estimator.

score = bbox volume of the whole assembly (mm^3) + 50 * vias + 5000 * copper layers

Copper layers are counted per board and the maximum is taken (stacked
single-layer boards still cost 5000). Volume comes from an STL export so the
parts' 3D models are included, not just the board outline.

usage:
    python score.py board.kicad_pcb [more.kicad_pcb ...] [--stl assembly.stl]

Without --stl each board is exported with kicad-cli and the boards are assumed
to sit in their own coordinate frames (good enough for a single board).
For a stack, export the assembly STL/STEP yourself and pass it with --stl.
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile

import numpy as np

from sexpr import parse, find, first, value

KICAD_CLI = os.environ.get(
    "KICAD_CLI",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\KiCad\10.0\bin\kicad-cli.exe"),
)

COPPER = lambda name: name.endswith(".Cu")


def stl_points(path):
    data = open(path, "rb").read()
    if data[:5] == b"solid" and b"facet" in data[:400]:
        pts = [
            list(map(float, line.split()[1:4]))
            for line in data.decode(errors="ignore").splitlines()
            if line.strip().startswith("vertex")
        ]
        return np.array(pts)
    (n,) = struct.unpack_from("<I", data, 80)
    rec = np.frombuffer(data, dtype=np.uint8, count=n * 50, offset=84).reshape(n, 50)
    tri = rec[:, 12:48].copy().view("<f4").reshape(n * 3, 3)
    return tri.astype(float)


def bbox(points):
    lo, hi = points.min(axis=0), points.max(axis=0)
    return lo, hi, float(np.prod(hi - lo))


def board_stats(path):
    root = parse(open(path, encoding="utf8").read())
    vias = len(find(root, "via"))
    used = set()
    for kind in ("segment", "arc"):
        for item in find(root, kind):
            used.add(value(item, "layer"))
    for zone in find(root, "zone"):
        if first(zone, "net") is not None and first(zone, "filled_polygon") is not None:
            for fp in find(zone, "filled_polygon"):
                used.add(value(fp, "layer"))
    for fp in find(root, "footprint"):
        for pad in find(fp, "pad"):
            layers = first(pad, "layers")
            if not layers:
                continue
            for name in layers[1:]:
                if name == "*.Cu":
                    # through-hole pad: only counts on layers that actually carry copper
                    continue
                used.add(name)
        # free-standing plated holes that aren't component legs count as vias
    copper = sorted(l for l in used if l and COPPER(l))
    return vias, copper


def export_stl(pcb, out):
    cmd = [KICAD_CLI, "pcb", "export", "stl", "--subst-models", "-f", "-o", out, pcb]
    subprocess.run(cmd, check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("boards", nargs="+")
    ap.add_argument("--stl", help="assembly STL (overrides per-board export)")
    args = ap.parse_args()

    total_vias, max_layers = 0, 0
    for b in args.boards:
        vias, copper = board_stats(b)
        total_vias += vias
        max_layers = max(max_layers, len(copper))
        print(f"{os.path.basename(b)}: vias={vias} copper={copper or '-'}")

    if args.stl:
        pts = stl_points(args.stl)
    else:
        chunks = []
        with tempfile.TemporaryDirectory() as tmp:
            for i, b in enumerate(args.boards):
                out = os.path.join(tmp, f"{i}.stl")
                export_stl(b, out)
                chunks.append(stl_points(out))
        pts = np.vstack(chunks)

    lo, hi, vol = bbox(pts)
    dims = hi - lo
    score = vol + 50 * total_vias + 5000 * max_layers
    print(f"bbox {dims[0]:.2f} x {dims[1]:.2f} x {dims[2]:.2f} mm = {vol:.0f} mm^3")
    print(f"vias {total_vias} (+{50 * total_vias}), layers {max_layers} (+{5000 * max_layers})")
    print(f"SCORE {score:.0f}")


if __name__ == "__main__":
    sys.exit(main())
