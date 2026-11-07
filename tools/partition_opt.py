"""Search for a good part -> board split for the 3-board stack.

usage: python tools/partition_opt.py <netlist> [--side 26] [--iters 200000] [--seed 1]

Cost = PIN_COST * (number of nets that touch more than one board)
     + OVER_COST * (area over each board's usable capacity)^2 (smooth, so the
       search can pass through slightly overfull states early on)

Every board-to-board pin goes through the whole stack, so a crossing net costs
the same whichever boards it touches. Part area is the footprint courtyard
(pads if there is no courtyard) times a routing factor for single layer.
Pinned parts (connectors, things that must be seen or pressed) never move.
"""
import argparse
import math
import os
import random
import re
from collections import defaultdict

from netlist import load
from sexpr import parse, find, first

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRETTY = os.path.join(ROOT, "pcbgolf.pretty")

ROUTING_FACTOR = 1.5      # single layer + jumpers needs room
PIN_AREA = 4.0            # mm^2 a 2 mm pitch pin + 1.7 mm NPTH pad takes on EVERY board
OVER_COST = 1.0

PINNED = {
    # edge connectors and the 12 V input stage
    **{r: "B0" for r in "J1 J3 J5 J6 J7 J8 D1 Q1 D2 R2".split()},
    # seen or touched from the top
    **{r: "B2" for r in ("LED1 LED2 LED3 LED4 LED5 LED6 LED7 LED8 LED9 LED10 LED11 LED12 "
                          "LED13 LED14 LED15 LED16 LED17 SW1 J2").split()},
}


def footprint_area(fp_name, cache={}):
    if fp_name in cache:
        return cache[fp_name]
    path = os.path.join(PRETTY, fp_name.split(":")[-1] + ".kicad_mod")
    mod = parse(open(path, encoding="utf8").read())
    xs, ys = [], []
    for kind in ("fp_line", "fp_rect", "fp_poly"):
        for g in find(mod, kind):
            if first(g, "layer") and first(g, "layer")[1] in ("F.CrtYd", "B.CrtYd"):
                for pt in re.findall(r"\(\s*(?:start|end|xy) ([-\d.]+) ([-\d.]+)", str(g).replace("'", "")):
                    pass
                for sub in g[1:]:
                    if isinstance(sub, list) and sub[0] in ("start", "end"):
                        xs.append(float(sub[1])); ys.append(float(sub[2]))
                    if isinstance(sub, list) and sub[0] == "pts":
                        for xy in sub[1:]:
                            xs.append(float(xy[1])); ys.append(float(xy[2]))
    if not xs:
        for p in find(mod, "pad"):
            at, size = first(p, "at"), first(p, "size")
            x, y, w, h = float(at[1]), float(at[2]), float(size[1]), float(size[2])
            xs += [x - w / 2, x + w / 2]
            ys += [y - h / 2, y + h / 2]
    a = (max(xs) - min(xs)) * (max(ys) - min(ys)) if xs else 1.0
    cache[fp_name] = a
    return a


def capacities(side):
    full = side * side
    jack = 10.6 * 12.2              # jack column goes through every board
    ports = 5 * 9.4 * 8.6 + 12.2 * 12.0 * 0  # receptacles only on B0; SD is a B2 part
    return {"B0": full - jack - ports, "B1": full - jack, "B2": full - jack}


def evaluate(assign, net_members, area, cap):
    cross = 0
    for members in net_members:
        if len({assign[r] for r in members}) > 1:
            cross += 1
    used = defaultdict(float)
    for r, b in assign.items():
        used[b] += area[r]
    for b in cap:
        used[b] += cross * PIN_AREA        # every pin goes through the whole stack
    over = sum(max(0.0, used[b] - cap[b]) for b in cap)
    spread = max(used[b] / cap[b] for b in cap)   # keep the worst board as empty as possible
    return 1000 * spread + OVER_COST * over, cross, used, cross * PIN_AREA


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("netlist")
    ap.add_argument("--side", type=float, default=26.0)
    ap.add_argument("--iters", type=int, default=200000)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    random.seed(args.seed)

    parts, nets, _ = load(args.netlist)
    area = {}
    for r, p in parts.items():
        a = footprint_area(p["footprint"])
        # connectors are counted in the capacity, not as routable area
        area[r] = 0.0 if r in ("J1", "J3", "J5", "J6", "J7", "J8") else a * ROUTING_FACTOR
    net_members = [sorted({r for r, _, _ in m}) for m in nets.values() if len({r for r, _, _ in m}) > 1]
    cap = capacities(args.side)

    from partition import board_of
    assign = {r: PINNED.get(r, board_of(r)) for r in parts}
    movable = [r for r in parts if r not in PINNED]
    cost, cross, used, _ = evaluate(assign, net_members, area, cap)
    best = (cost, dict(assign))
    t0, t1 = 50.0, 0.05
    for i in range(args.iters):
        t = t0 * (t1 / t0) ** (i / args.iters)
        r = random.choice(movable)
        old = assign[r]
        assign[r] = random.choice([b for b in ("B0", "B1", "B2") if b != old])
        c2, _, _, _ = evaluate(assign, net_members, area, cap)
        if c2 <= cost or random.random() < math.exp((cost - c2) / t):
            cost = c2
            if cost < best[0]:
                best = (cost, dict(assign))
        else:
            assign[r] = old
    cost, assign = best
    cost, cross, used, _ = evaluate(assign, net_members, area, cap)
    print(f"side {args.side} mm: crossing nets {cross}")
    for b in ("B0", "B1", "B2"):
        refs = sorted((r for r in assign if assign[r] == b), key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0)))
        print(f"{b}: used {used[b]:.0f} / cap {cap[b]:.0f} mm^2, {len(refs)} parts")
        print("   " + " ".join(refs))


if __name__ == "__main__":
    main()
