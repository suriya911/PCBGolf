"""Which part lives on which board of the stack, and what that costs in interconnect.

usage: python tools/partition.py <netlist>

B0  bottom, 0.6 mm: every connector that mates sideways (USB-C x5, DC jack),
    the 12 V input stage and the per-port eFuses - the high current never
    leaves this board.
B1  middle: MCU, USB hubs, both bucks, CAN transceivers/chokes/comparators.
B2  top: everything that has to be seen or touched - all LEDs, the button,
    the microSD slot - plus the SBU ignition/relay switches and their
    pull-downs which sit right under their indicator LEDs.

A net that has pads on more than one board needs board-to-board pins; the
report lists them per board pair so the split can be tuned.
"""
import re
import sys
from collections import defaultdict

from netlist import load

B0 = """J1 J3 J5 J6 J7 J8 D1 Q1 D2 R2 C3 C5 C29 R31 R44
U13 U14 U15 U16 R66 R67 R68 R69 R70 R71 R72 R73 C50 C51 C52 C53
R46 R47 R48 R49"""

B2 = """LED1 LED2 LED3 LED4 LED5 LED6 LED7 LED8 LED9
LED10 LED11 LED12 LED13 LED14 LED15 LED16 LED17
R21 R22 R23 R62 R63 R64 R65 R74 R75 R76 R77
R82 R83 R84 R85 R86 R87 R88 R89 R106 R107 R108 R109 R110 R111 R112 R113
SW1 R12 J2 R33 R34 R35 R36 R37 C37
Q2 Q3 Q4 Q5 Q6 Q7 Q8 Q9 R90 R91 R92 R93 R94 R95 R96 R97
R114 R115 R116 R117 R118 R119 R120 R121
R78 R79 R80 R81 R98 R99 R100 R101 R102 R103 R104 R105 R122 R123 R124 R125"""

ASSIGN = {}
for board, refs in (("B0", B0), ("B2", B2)):
    for r in refs.split():
        ASSIGN[r] = board


def board_of(ref):
    return ASSIGN.get(ref, "B1")


def crossings(nets):
    out = defaultdict(list)
    for name, members in nets.items():
        boards = sorted({board_of(r) for r, _, _ in members})
        if len(boards) > 1:
            out[tuple(boards)].append(name)
    return out


def main(netfile):
    parts, nets, _ = load(netfile)
    counts = defaultdict(int)
    for r in parts:
        counts[board_of(r)] += 1
    print("parts per board:", dict(sorted(counts.items())))
    cross = crossings(nets)
    total = 0
    for pair, names in sorted(cross.items()):
        total += len(names)
        print(f"{'-'.join(pair)}: {len(names)} nets")
        print("   " + " ".join(sorted(names, key=lambda n: re.sub(r'\d+', lambda m: m.group().zfill(3), n))))
    print("total crossing nets:", total)


if __name__ == "__main__":
    main(sys.argv[1])
