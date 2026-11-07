"""Check that a modified design still has the same connectivity as the original.

Nets are compared as sets of (ref, pin) - net names are allowed to change.
Part swaps are described with pin translation tables so e.g. an LQFP-144 pin 21
(PF7) can be matched against LQFP-100 pin 27 (PA2).

usage: python netcheck.py original.net modified.net [--map swaps.py]
"""
import argparse
import importlib.util
import re
import sys

from netlist import load


def by_name(nets, ref):
    """pin number -> pin name for one part (from netlist pinfunction)."""
    out = {}
    for members in nets.values():
        for r, p, fn in members:
            if r == ref and fn:
                out[p] = re.split(r"[(/]", fn.rsplit("_", 1)[0])[0]
    return out


def partition(nets, translate=lambda r, p: (r, p), drop=()):
    groups = []
    for name, members in nets.items():
        g = set()
        for r, p, _ in members:
            if r in drop:
                continue
            t = translate(r, p)
            if t is not None:
                g.add(t)
        if len(g) > 1:
            groups.append(frozenset(g))
    return set(groups)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("orig")
    ap.add_argument("new")
    ap.add_argument("--map", help="python file defining translate(ref, pin, ctx) and DROP")
    args = ap.parse_args()

    _, onets, _ = load(args.orig)
    _, nnets, _ = load(args.new)

    drop = set()
    translate = lambda r, p: (r, p)
    if args.map:
        spec = importlib.util.spec_from_file_location("swapmap", args.map)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        drop = set(getattr(mod, "DROP", ()))
        ctx = {"orig": onets, "new": nnets, "by_name": by_name}
        translate = lambda r, p: mod.translate(r, p, ctx, "orig")
        translate_new = lambda r, p: mod.translate(r, p, ctx, "new")
    else:
        translate_new = translate

    a = partition(onets, translate, drop)
    b = partition(nnets, translate_new, drop)
    missing = a - b
    extra = b - a
    for g in sorted(missing, key=lambda g: sorted(g)):
        print("ORIG ONLY:", sorted(g))
    for g in sorted(extra, key=lambda g: sorted(g)):
        print("NEW ONLY: ", sorted(g))
    print(f"{len(a)} nets checked, {len(missing)} missing, {len(extra)} new")
    return 1 if (missing or extra) else 0


if __name__ == "__main__":
    sys.exit(main())
