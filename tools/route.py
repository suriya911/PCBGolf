"""Autoroute one board on its single copper layer with Freerouting.

Run with KiCad's Python:
    python tools/route.py pcbgolf_B0.kicad_pcb [passes]

1. export Specctra DSN from the board
2. patch it: drop B.Cu (single copper layer, no vias), JLC 1-layer rules
   (0.127 mm / 0.127 mm), a wider class for the supply and port power nets
3. run Freerouting headless
4. import the session back and report what is still unrouted
Unrouted connections are left for the jumper pass (tools/jumpers.py).
"""
import os
import re
import subprocess
import sys

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FR = os.path.join(ROOT, "scratch", "fr", "freerouting-2.5.0.jar")
JRE = os.path.join(ROOT, "scratch", "jre")

TRACK_UM = 127
CLEAR_UM = 127
POWER_UM = 400
POWER_NETS = re.compile(r"^(\+12V|\+5V|\+3V3|GND|VBUS|VDDLDO|Net-\(J\d+-VBUS.*|Net-\(J1-PWR\))$")


def java():
    for d in sorted(os.listdir(JRE), reverse=True):
        if d.startswith("jdk-25"):
            return os.path.join(JRE, d, "bin", "java.exe")
    raise SystemExit("no Java 25 runtime in scratch/jre")


def patch_dsn(text, nets, name="board"):
    # KiCad writes the full output path as the design name; Freerouting chokes on "E:\..."
    text = re.sub(r"^\(pcb [^\n]*", f"(pcb {name}", text, count=1)
    # single layer: remove the B.Cu layer block and any via definition
    text = re.sub(r"\(layer B\.Cu\s*\(type signal\)\s*\(property\s*\(index 1\)\s*\)\s*\)", "", text)
    text = re.sub(r'\s*\(via "[^"]*"\)', "", text, count=1)
    text = re.sub(r"\(rule\s*\(width \d+\)\s*\(clearance \d+\)",
                  f"(rule\n      (width {TRACK_UM})\n      (clearance {CLEAR_UM})", text, count=1)
    # KiCad's default net class carries its own width; force the JLC minimum there too
    text = re.sub(r"\(width \d+\)", f"(width {TRACK_UM})", text)
    text = re.sub(r"\(clearance \d+\)", f"(clearance {CLEAR_UM})", text)
    power = [n for n in nets if POWER_NETS.match(n)]
    if power:
        names = " ".join(f'"{n}"' for n in power)
        cls = (f'    (class power {names}\n      (circuit (use_layer F.Cu))\n'
               f'      (rule (width {POWER_UM}) (clearance {CLEAR_UM}))\n    )\n')
        text = re.sub(r"(\(network\s*\n)", r"\1" + cls.replace("\\", "\\\\"), text, count=1)
    return text


def import_ses(board, ses_path):
    """Add the session's wires as tracks. (pcbnew.ImportSpecctraSES only works inside the GUI.)"""
    sys.path.insert(0, os.path.dirname(__file__))
    from sexpr import parse, find, first
    root = parse(open(ses_path).read())
    routes = first(root, "routes")
    res = first(routes, "resolution")
    scale = {"um": 1e-3, "mm": 1.0, "mil": 0.0254}[res[1]] / float(res[2])   # file units -> mm
    nets = board.GetNetsByName()
    added = 0
    for net in find(first(routes, "network_out"), "net"):
        info = nets[net[1]] if nets.has_key(net[1]) else None
        for wire in find(net, "wire"):
            path = first(wire, "path")
            layer = pcbnew.F_Cu if path[1] == "F.Cu" else pcbnew.B_Cu
            width = float(path[2]) * scale
            pts = [(float(path[i]) * scale, -float(path[i + 1]) * scale) for i in range(3, len(path) - 1, 2)]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
                t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
                t.SetWidth(pcbnew.FromMM(width))
                t.SetLayer(layer)
                if info is not None:
                    t.SetNet(info)
                board.Add(t)
                added += 1
    return added


def pour_gnd(board, w, h, inset=0.25):
    """Fill the free copper with GND - on one layer this is most of the ground connection."""
    nets = board.GetNetsByName()
    if not nets.has_key("GND"):
        return
    for z in list(board.Zones()):
        board.Remove(z)
    zone = pcbnew.ZONE(board)
    zone.SetLayer(pcbnew.F_Cu)
    zone.SetNet(nets["GND"])
    zone.SetLocalClearance(pcbnew.FromMM(0.2))
    zone.SetMinThickness(pcbnew.FromMM(0.15))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in ((inset, inset), (w - inset, inset), (w - inset, h - inset), (inset, h - inset)):
        outline.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    board.Add(zone)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def board_size(board):
    bb = board.GetBoardEdgesBoundingBox()
    return pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())


def unrouted(board):
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    return conn.GetUnconnectedCount(False)


def main(pcb, passes=20):
    board = pcbnew.LoadBoard(pcb)
    base = os.path.splitext(os.path.basename(pcb))[0]
    work = os.path.join(ROOT, "scratch", "fr")
    dsn = os.path.join(work, base + ".dsn")
    ses = os.path.join(work, base + ".ses")
    pcbnew.ExportSpecctraDSN(board, dsn)
    nets = [n for n in board.GetNetsByName().keys() if str(n)]
    nets = [str(n) for n in nets]
    patched = patch_dsn(open(dsn).read(), nets, base)
    open(dsn, "w").write(patched)
    if os.path.exists(ses):
        os.remove(ses)
    before = unrouted(board)
    cmd = [java(), "-jar", FR, "-de", dsn, "-do", ses, "-mp", str(passes), "--gui.enabled=false"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(ses):
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit("freerouting produced no session")
    for trk in list(board.GetTracks()):
        board.Delete(trk)
    n = import_ses(board, ses)
    print(f"imported {n} track segments")
    routed = unrouted(board)
    pour_gnd(board, *board_size(board))
    after = unrouted(board)
    print(f"after routing {routed}, after GND pour {after}")
    board.Save(pcb)
    print(f"{base}: unrouted connections {before} -> {after}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 20)
