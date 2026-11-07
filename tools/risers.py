"""Board-to-board risers: columns of pins running through the whole stack.

Every riser pin is a 2.0 mm pitch header pin (0.5 mm square) that goes from
the bottom board to the top board. On each board the pin either lands on a
copper pad (the board uses that net) or passes through a plain clearance hole.
JLC single-layer boards only have non-plated holes, and their rule for a pad
around an NPTH hole is a 0.45 mm ring, hence 0.8 mm hole / 1.7 mm pad.

risers.json: {"P1": {"at": [x, y], "dir": "x"|"y", "rows": 2, "nets": [...]}, ...}
A net may appear in several groups (e.g. GND) - list it as "GND", "GND#2"... the
part after # is ignored when looking up the net.
Pins fill the grid row by row starting at "at" (pin 1), 2.0 mm apart.
"""
import json

PITCH = 2.0
HOLE = 0.8
PAD = 1.7
CLEAR_HOLE = 0.9


def net_name(label):
    return label.split("#")[0]


def pin_positions(spec):
    x0, y0 = spec["at"]
    rows = spec.get("rows", 1)
    cols = -(-len(spec["nets"]) // rows)
    out = []
    for i, net in enumerate(spec["nets"]):
        r, c = divmod(i, cols)
        if spec.get("dir", "x") == "x":
            out.append((net, x0 + c * PITCH, y0 + r * PITCH))
        else:
            out.append((net, x0 + r * PITCH, y0 + c * PITCH))
    return out


def load(path):
    return json.load(open(path))


ORDER = ["B0", "B1", "B2"]


def pin_role(net, board_name, boards_of_net, span=None):
    """'pad' if this board solders the pin, 'hole' if the pin just passes through, None if absent.
    span: optional list of boards the whole group is limited to (e.g. GND pins of a
    B1-B2 riser must not reach down to B0 just because B0 also has GND)."""
    if span is not None and board_name not in span:
        return None
    used = sorted(ORDER.index(b) for b in boards_of_net(net_name(net)) if span is None or b in span)
    me = ORDER.index(board_name)
    if me in used:
        return "pad"
    if used and used[0] < me < used[-1]:
        return "hole"
    return None


def add_to_board(board, risers, board_name, boards_of_net, netinfo):
    """Add one footprint per riser group to a pcbnew board."""
    import pcbnew

    def mm(v):
        return pcbnew.FromMM(v)

    for name, spec in risers.items():
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(name)
        fp.SetValue("riser")
        fp.SetAttributes(pcbnew.FP_THROUGH_HOLE)
        sp = spec.get("span")
        pins = [(n, x, y) for n, x, y in pin_positions(spec) if pin_role(n, board_name, boards_of_net, sp)]
        if not pins:
            continue
        x0, y0 = spec["at"]
        fp.SetPosition(pcbnew.VECTOR2I(mm(x0), mm(y0)))
        numbers = {n: i for i, (n, _, _) in enumerate(pin_positions(spec), 1)}
        for net, x, y in pins:
            i = numbers[net]
            pad = pcbnew.PAD(fp)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
            pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            if pin_role(net, board_name, boards_of_net, sp) == "pad":
                # NPTH with a copper ring on F.Cu: the pin is soldered on the copper side
                pad.SetSize(pcbnew.VECTOR2I(mm(PAD), mm(PAD)))
                pad.SetDrillSize(pcbnew.VECTOR2I(mm(HOLE), mm(HOLE)))
                lset = pcbnew.LSET()
                lset.AddLayer(pcbnew.F_Cu)
                lset.AddLayer(pcbnew.F_Mask)
                pad.SetLayerSet(lset)
                pad.SetNumber(str(i))
                pad.SetNet(netinfo[net_name(net)])
            else:
                pad.SetSize(pcbnew.VECTOR2I(mm(CLEAR_HOLE), mm(CLEAR_HOLE)))
                pad.SetDrillSize(pcbnew.VECTOR2I(mm(CLEAR_HOLE), mm(CLEAR_HOLE)))
                pad.SetLayerSet(pcbnew.LSET.AllCuMask())
                pad.SetNumber("")
            pad.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
            fp.Add(pad)
        # courtyard so the placer keeps parts off the pins
        xs = [p[1] for p in pins]
        ys = [p[2] for p in pins]
        m = PAD / 2 + 0.1
        rect = pcbnew.PCB_SHAPE(fp)
        rect.SetShape(pcbnew.SHAPE_T_RECT)
        rect.SetStart(pcbnew.VECTOR2I(mm(min(xs) - m), mm(min(ys) - m)))
        rect.SetEnd(pcbnew.VECTOR2I(mm(max(xs) + m), mm(max(ys) + m)))
        rect.SetLayer(pcbnew.F_CrtYd)
        rect.SetWidth(mm(0.05))
        fp.Add(rect)
        board.Add(fp)
