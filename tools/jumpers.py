"""Finish a single-layer board: route what Freerouting left, hopping over traces with 0R jumpers.

Run with KiCad's Python:
    python tools/jumpers.py <board.kicad_pcb> [--first-ref 201]

Grid router on F.Cu (0.05 mm cells). Every copper item is rasterised with its
clearance; a cell belongs to one net, to nobody, or is blocked. A* connects
islands of the same net. Besides the 8 normal moves, a path may jump straight
over anything with a 0R resistor (0402/0603/0805/1206 pad spacing); a jump is
legal when both pads fit on free copper and the resistor body does not land on
another component. Jumps cost a lot, so they are only used where a plain trace
cannot get through. Each jump becomes a real 0R footprint (refs R201...)
with both pads on the net, so it shows up in the BOM and in DRC.
"""
import heapq
import math
import os
import sys

import numpy as np
import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
from route import pour_gnd, board_size, unrouted   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "pcbgolf.pretty")

GRID = 0.1
CLEAR = 0.127
EDGE = 0.2
HOLE_CLEAR = 0.2
SIGNAL_W = 0.127
POWER_W = 0.3
POWER = ("+12V", "+5V", "+3V3", "GND", "VBUS", "VDDLDO", "Net-(J1-PWR)")

# name, footprint, half pad spacing (mm), pad size (mm), body (courtyard) size, MPN
JUMPERS = [
    ("0402", "R_0402_1005Metric", 0.51, (0.54, 0.64), (1.86, 0.94), "RC0402JR-070RL"),
    ("0603", "R_0603_1608Metric", 0.825, (0.80, 0.95), (2.96, 1.46), "RC0603JR-070RL"),
    ("0805", "R_0805_2012Metric", 0.9125, (1.025, 1.40), (3.36, 1.90), "RC0805JR-070RL"),
    ("1206", "R_1206_3216Metric", 1.4625, (1.125, 1.75), (4.56, 2.30), "RC1206JR-070RL"),
]
JUMP_COST = 60.0


def mm(v):
    return pcbnew.FromMM(v)


def to_mm(v):
    return pcbnew.ToMM(v)


def is_power(net):
    return net in POWER or net.startswith("Net-(J") and "VBUS" in net


class Raster:
    def __init__(self, w, h):
        self.nx, self.ny = int(math.ceil(w / GRID)), int(math.ceil(h / GRID))
        self.owner = np.zeros((self.ny, self.nx), dtype=np.int32)    # 0 free, >0 net, -1 blocked
        self.body = np.zeros((self.ny, self.nx), dtype=bool)         # component courtyards
        self.xs = (np.arange(self.nx) + 0.5) * GRID
        self.ys = (np.arange(self.ny) + 0.5) * GRID

    def window(self, x0, y0, x1, y1):
        i0, i1 = max(0, int(x0 / GRID)), min(self.nx, int(x1 / GRID) + 2)
        j0, j1 = max(0, int(y0 / GRID)), min(self.ny, int(y1 / GRID) + 2)
        return i0, i1, j0, j1

    def claim(self, mask_slice, sl, net):
        cur = self.owner[sl]
        cur[mask_slice & (cur == 0)] = net
        cur[mask_slice & (cur > 0) & (cur != net)] = -1
        self.owner[sl] = cur

    def box(self, x0, y0, x1, y1, net, grow):
        i0, i1, j0, j1 = self.window(x0 - grow, y0 - grow, x1 + grow, y1 + grow)
        X, Y = np.meshgrid(self.xs[i0:i1], self.ys[j0:j1])
        dx = np.maximum(np.maximum(x0 - X, X - x1), 0)
        dy = np.maximum(np.maximum(y0 - Y, Y - y1), 0)
        m = np.hypot(dx, dy) <= grow
        self.claim(m, (slice(j0, j1), slice(i0, i1)), net)

    def segment(self, ax, ay, bx, by, r, net):
        i0, i1, j0, j1 = self.window(min(ax, bx) - r, min(ay, by) - r, max(ax, bx) + r, max(ay, by) + r)
        X, Y = np.meshgrid(self.xs[i0:i1], self.ys[j0:j1])
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        t = np.clip(((X - ax) * vx + (Y - ay) * vy) / L2, 0, 1) if L2 > 0 else 0
        d = np.hypot(X - (ax + t * vx), Y - (ay + t * vy))
        self.claim(d <= r, (slice(j0, j1), slice(i0, i1)), net)

    def cell(self, x, y):
        return min(self.nx - 1, max(0, int(x / GRID))), min(self.ny - 1, max(0, int(y / GRID)))


def build_raster(board, w, h, track_w):
    R = Raster(w, h)
    grow_t = CLEAR + track_w / 2
    edge = int(math.ceil((EDGE + track_w / 2) / GRID))
    R.owner[:edge, :] = -1
    R.owner[-edge:, :] = -1
    R.owner[:, :edge] = -1
    R.owner[:, -edge:] = -1
    for fp in board.GetFootprints():
        try:
            cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
            i0, i1, j0, j1 = R.window(to_mm(cy.GetLeft()), to_mm(cy.GetTop()), to_mm(cy.GetRight()), to_mm(cy.GetBottom()))
            R.body[j0:j1, i0:i1] = True
        except Exception:
            pass
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            x0, y0, x1, y1 = to_mm(bb.GetLeft()), to_mm(bb.GetTop()), to_mm(bb.GetRight()), to_mm(bb.GetBottom())
            on_cu = pad.IsOnLayer(pcbnew.F_Cu)
            net = pad.GetNetCode()
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH and pad.HasHole():
                d = to_mm(pad.GetDrillSizeX())
                c = pad.GetPosition()
                cx, cy2 = to_mm(c.x), to_mm(c.y)
                R.box(cx - d / 2, cy2 - d / 2, cx + d / 2, cy2 + d / 2, -1, HOLE_CLEAR + track_w / 2)
            if on_cu:
                R.box(x0, y0, x1, y1, net if net > 0 else -1, grow_t)
    for t in board.GetTracks():
        if t.GetLayer() != pcbnew.F_Cu:
            continue
        a, b = t.GetStart(), t.GetEnd()
        r = to_mm(t.GetWidth()) / 2 + grow_t
        R.segment(to_mm(a.x), to_mm(a.y), to_mm(b.x), to_mm(b.y), r, t.GetNetCode())
    return R


def islands(board, net):
    """Groups of copper items of one net that are already connected."""
    items = [p for p in board.GetPads() if p.GetNetCode() == net and p.IsOnLayer(pcbnew.F_Cu)]
    tracks = [t for t in board.GetTracks() if t.GetNetCode() == net and t.GetLayer() == pcbnew.F_Cu]
    n = len(items) + len(tracks)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        parent[find(a)] = find(b)

    for ti, t in enumerate(tracks):
        k = len(items) + ti
        for end in (t.GetStart(), t.GetEnd()):
            for pi, p in enumerate(items):
                if p.HitTest(end):
                    union(k, pi)
            for tj, u in enumerate(tracks):
                if tj != ti and u.HitTest(end, t.GetWidth() // 2):
                    union(k, len(items) + tj)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(items[i] if i < len(items) else tracks[i - len(items)])
    return list(groups.values())


def item_cells(R, item):
    if isinstance(item, pcbnew.PAD):
        bb = item.GetBoundingBox()
        i0, i1, j0, j1 = R.window(to_mm(bb.GetLeft()), to_mm(bb.GetTop()), to_mm(bb.GetRight()), to_mm(bb.GetBottom()))
        c = item.GetPosition()
        out = [R.cell(to_mm(c.x), to_mm(c.y))]
        for j in range(j0, j1):
            for i in range(i0, i1):
                p = pcbnew.VECTOR2I(mm((i + 0.5) * GRID), mm((j + 0.5) * GRID))
                if item.HitTest(p):          # only cells really inside the pad copper
                    out.append((i, j))
        return out
    a, b = item.GetStart(), item.GetEnd()
    ax, ay, bx, by = to_mm(a.x), to_mm(a.y), to_mm(b.x), to_mm(b.y)
    n = max(1, int(math.hypot(bx - ax, by - ay) / GRID))
    return [R.cell(ax + (bx - ax) * k / n, ay + (by - ay) * k / n) for k in range(n + 1)]


def window_all(mask, ri, rj):
    """True where the (2ri+1)x(2rj+1) window centred on the cell is entirely True (summed-area table)."""
    ny, nx = mask.shape
    S = np.zeros((ny + 1, nx + 1), dtype=np.int32)
    S[1:, 1:] = np.cumsum(np.cumsum(mask.astype(np.int32), 0), 1)
    out = np.zeros_like(mask)
    j0, j1 = rj, ny - rj
    i0, i1 = ri, nx - ri
    if j1 <= j0 or i1 <= i0:
        return out
    J, I = np.mgrid[j0:j1, i0:i1]
    tot = S[J + rj + 1, I + ri + 1] - S[J - rj, I + ri + 1] - S[J + rj + 1, I - ri] + S[J - rj, I - ri]
    out[j0:j1, i0:i1] = tot == (2 * ri + 1) * (2 * rj + 1)
    return out


def jump_maps(R, net, jumps):
    """Per jumper and orientation: where a pad fits, and where the body is free."""
    free = (R.owner == 0) | (R.owner == net)
    nobody = ~R.body
    maps = []
    for jumper in jumps:
        L = int(round(2 * jumper[2] / GRID))
        pw, ph = jumper[3]
        bw, bh = jumper[4]
        for d in ((1, 0), (0, 1)):
            w, hgt = (pw, ph) if d[0] else (ph, pw)
            # other copper in `owner` is already grown by its clearance, so only the pad itself must be free
            pad = window_all(free, int(math.ceil(w / 2 / GRID)), int(math.ceil(hgt / 2 / GRID)))
            bwid, bhgt = (bw, bh) if d[0] else (bh, bw)
            body = window_all(nobody, int(bwid / 2 / GRID), int(bhgt / 2 / GRID))
            maps.append((jumper, d, L, pad, body))
    return maps


def search(R, net, sources, targets, jumps):
    """A* from the source cells to any target cell; returns (path, prev) or None."""
    tset = set(targets)
    if not tset:
        return None
    tx0 = min(t[0] for t in tset)
    tx1 = max(t[0] for t in tset)
    ty0 = min(t[1] for t in tset)
    ty1 = max(t[1] for t in tset)

    def h(c):
        return math.hypot(max(tx0 - c[0], 0, c[0] - tx1), max(ty0 - c[1], 0, c[1] - ty1))

    passable = (R.owner == 0) | (R.owner == net)
    maps = jump_maps(R, net, jumps)
    nx, ny = R.nx, R.ny
    g, prev, heap, closed = {}, {}, [], set()
    for s in set(sources):
        g[s] = 0.0
        heapq.heappush(heap, (h(s), s))
    steps = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, 1.42), (1, -1, 1.42), (-1, 1, 1.42), (-1, -1, 1.42)]
    budget = 400000
    while heap and budget:
        budget -= 1
        _, c = heapq.heappop(heap)
        if c in closed:
            continue
        closed.add(c)
        if c in tset:
            path = [c]
            while path[-1] in prev:
                path.append(prev[path[-1]][0])
            path.reverse()
            return path, prev
        gc = g[c]
        i, j = c
        for di, dj, cost in steps:
            ni, nj = i + di, j + dj
            if 0 <= ni < nx and 0 <= nj < ny and passable[nj, ni]:
                n = (ni, nj)
                if gc + cost < g.get(n, 1e18):
                    g[n] = gc + cost
                    prev[n] = (c, None)
                    heapq.heappush(heap, (g[n] + h(n), n))
        for jumper, d, L, pad, body in maps:
            if not pad[j, i]:
                continue
            for sgn in (1, -1):
                ni, nj = i + sgn * d[0] * L, j + sgn * d[1] * L
                if not (0 <= ni < nx and 0 <= nj < ny) or not pad[nj, ni]:
                    continue
                if not body[(j + nj) // 2, (i + ni) // 2]:
                    continue
                n = (ni, nj)
                cost = JUMP_COST + L
                if gc + cost < g.get(n, 1e18):
                    g[n] = gc + cost
                    prev[n] = (c, jumper)
                    heapq.heappush(heap, (g[n] + h(n), n))
    return None


def commit(board, R, net_item, path, prev, track_w, refs, jumper_fps):
    """Turn the cell path into tracks and 0R footprints; update the raster."""
    netcode = net_item.GetNetCode()
    run = [path[0]]
    pieces = []
    for c in path[1:]:
        jumper = prev[c][1]
        if jumper is None:
            run.append(c)
        else:
            pieces.append(("trace", run))
            pieces.append(("jump", (run[-1], c, jumper)))
            run = [c]
    pieces.append(("trace", run))
    for kind, data in pieces:
        if kind == "trace":
            pts = data
            if len(pts) < 2:
                continue
            # keep only the corners
            corners = [pts[0]]
            for k in range(1, len(pts) - 1):
                d1 = (pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1])
                d2 = (pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1])
                if d1 != d2:
                    corners.append(pts[k])
            corners.append(pts[-1])
            for a, b in zip(corners, corners[1:]):
                ax, ay = (a[0] + 0.5) * GRID, (a[1] + 0.5) * GRID
                bx, by = (b[0] + 0.5) * GRID, (b[1] + 0.5) * GRID
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(mm(ax), mm(ay)))
                t.SetEnd(pcbnew.VECTOR2I(mm(bx), mm(by)))
                t.SetWidth(mm(track_w))
                t.SetLayer(pcbnew.F_Cu)
                t.SetNet(net_item)
                board.Add(t)
                R.segment(ax, ay, bx, by, track_w / 2 + CLEAR + track_w / 2, netcode)
        else:
            a, b, jumper = data
            ax, ay = (a[0] + 0.5) * GRID, (a[1] + 0.5) * GRID
            bx, by = (b[0] + 0.5) * GRID, (b[1] + 0.5) * GRID
            fp = pcbnew.FootprintLoad(LIB, jumper[1])
            ref = f"R{refs[0]}"
            refs[0] += 1
            fp.SetReference(ref)
            fp.SetValue("0R")
            fp.SetPosition(pcbnew.VECTOR2I(mm((ax + bx) / 2), mm((ay + by) / 2)))
            fp.SetOrientationDegrees(0 if a[1] == b[1] else 90)
            for pad in fp.Pads():
                pad.SetNet(net_item)
            board.Add(fp)
            jumper_fps.append((ref, jumper[0], jumper[5], net_item.GetNetname()))
            for pad in fp.Pads():
                bb = pad.GetBoundingBox()
                R.box(to_mm(bb.GetLeft()), to_mm(bb.GetTop()), to_mm(bb.GetRight()), to_mm(bb.GetBottom()),
                      netcode, CLEAR + track_w / 2)
            cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
            i0, i1, j0, j1 = R.window(to_mm(cy.GetLeft()), to_mm(cy.GetTop()), to_mm(cy.GetRight()), to_mm(cy.GetBottom()))
            R.body[j0:j1, i0:i1] = True


def main(pcb, first_ref=201):
    board = pcbnew.LoadBoard(pcb)
    for z in list(board.Zones()):
        board.Delete(z)
    w, h = board_size(board)
    nets = board.GetNetsByName()
    jumper_fps = []
    refs = [first_ref]
    failed = []
    for track_w, pick in ((POWER_W, True), (SIGNAL_W, False)):
        R = build_raster(board, w, h, track_w)
        for name in sorted(str(n) for n in nets.keys()):
            if not name or name.startswith("unconnected") or is_power(name) != pick or name == "GND":
                continue
            net_item = nets[name]
            code = net_item.GetNetCode()
            groups = islands(board, code)
            while len(groups) > 1:
                groups.sort(key=len, reverse=True)
                src = [c for it in groups[0] for c in item_cells(R, it)]
                tgt = [c for grp in groups[1:] for it in grp for c in item_cells(R, it)]
                res = search(R, code, src, tgt, JUMPERS)
                if res is None:
                    failed.append(name)
                    print(f"  {name}: no path", flush=True)
                    break
                print(f"  {name}: connected ({len(groups) - 1} islands left before)", flush=True)
                path, prev = res
                commit(board, R, net_item, path, prev, track_w, refs, jumper_fps)
                groups = islands(board, code)
    pour_gnd(board, w, h)
    left = unrouted(board)
    board.Save(pcb)
    print(f"jumpers added: {len(jumper_fps)}, nets that failed: {sorted(set(failed))}, unrouted now {left}")
    with open(pcb.replace(".kicad_pcb", "_jumpers.txt"), "w") as f:
        for ref, size, mpn, net in jumper_fps:
            f.write(f"{ref}\t{size}\t{mpn}\t{net}\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    first = 201
    if "--first-ref" in args:
        first = int(args[args.index("--first-ref") + 1])
    main(args[0], first)
