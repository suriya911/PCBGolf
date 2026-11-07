"""Load a KiCad netlist into plain dicts and dump per-part pin maps."""
import sys
from sexpr import parse, find, first, value


def load(path):
    root = parse(open(path, encoding="utf8").read())
    parts = {}
    for comp in find(first(root, "components"), "comp"):
        ref = value(comp, "ref")
        props = {value(p, "name"): value(p, "value") for p in find(comp, "property")}
        parts[ref] = {
            "value": value(comp, "value"),
            "footprint": value(comp, "footprint"),
            "props": props,
        }
    nets = {}
    pins = {}  # (ref, pin) -> net
    for net in find(first(root, "nets"), "net"):
        name = value(net, "name")
        members = []
        for node in find(net, "node"):
            ref, pin = value(node, "ref"), value(node, "pin")
            members.append((ref, pin, value(node, "pinfunction")))
            pins[(ref, pin)] = name
        nets[name] = members
    return parts, nets, pins


if __name__ == "__main__":
    parts, nets, pins = load(sys.argv[1])
    ref = sys.argv[2]
    rows = []
    for name, members in nets.items():
        for r, p, fn in members:
            if r == ref:
                rows.append((p, fn or "", name, len(members)))
    def key(row):
        p = row[0]
        return (0, int(p)) if p.isdigit() else (1, p)
    for p, fn, name, n in sorted(rows, key=key):
        print(f"{p:>4} {fn:22s} {name:34s} fanout={n}")
